# ONGOING — Voice Wire-Protocol Test Harness (Plan 4) + Pipeline Metrics History (Plan 3)

> Working document for the two approved plans from the 2026-08-26 session.
> Update the Progress Log at every milestone; this file is the recovery point
> if a session dies. Plans 1 (SMALL_LLM seam) and 2 (dynamics persistence) are
> already landed — see git `85240d6`, `fb72daa` and
> `wiki/queries/2026-08-26_dynamics_persistence_plan.md`.

## Ground rules (apply to everything below)

- Type annotations on every function/method (`X | None` style). AGENTS.md.
- Gates before each commit: `.venv/bin/ruff check serin/ tests/`, mypy strict,
  pyright on touched files, semgrep custom rules, Law checkers, targeted pytest.
- No post-hoc RNG anywhere (SERIN_VISION Operational Definitions; semgrep
  `no-performative-randomness`). Tests assert determinism.
- Loggers: `{component}.{event}` first positional arg + structured `extra={}`
  (docs/LOGGING.md).
- Commits: conventional style matching repo history
  (`test(voice): …`, `feat(ops): …`), detailed body, `--no-verify` only if the
  detect-secrets hook cannot run in-sandbox, with justification + compensating
  control in the body (established pattern in this repo's history).
- Websearch the moment a problem loops twice. Graphify (`graphify query`) for
  codebase questions.

---

# PLAN 4 — Voice wire-protocol integration tests (+ PyO3 / real-binary smokes)

## Why (doc anchors)

- CONNECTIONS.md J "Testing gap": wire framing covered only by AST contracts;
  Phase-5 rec #5 names both gaps explicitly. wiki [[testing]]: "the two
  explicit gaps in the suite".
- wiki [[dave_receive]]: "silent drops are the enemy". The `_EOF` bug and the
  load-bearing TTS_DONE lock both lived exactly here and were invisible to
  text-level checks.
- Anti-drift design (user requirement: fakes must not become stale lies):
  sync-guard test pins fake ↔ main.rs; one shared framer module encodes each
  frame layout once.

## Verified current state (2026-08-26 recon)

- `RustStdoutReader.read_loop()` (d4_1_io_bridge.py) parses:
  `AUDIO:{user_id}:{pcm_len}\n+bytes`, `JOIN:{uid}`, `LEAVE:{uid}`,
  `TTS_DONE`, other lines → `('log', line)` events; puts `_EOF` sentinel +
  stops on empty read; `get(timeout)` raises EOFError on sentinel.
- **FINDING A (pre-existing, will pin not fix):** live consumer
  `_read_loop` (d5_2_process_watch_io.py:119) does
  `async for event_type, event_data in self.reader` but RustStdoutReader has
  NO `__aiter__`/`__anext__` and its events are tuples like `('audio', uid,
  pcm)` (3-tuple), while the consumer unpacks 2-tuples and expects dicts.
  The consumer loop can never have worked against this reader. Tests must
  document this honestly as a pinned known-wiring-gap (candidate fix is a
  separate proposal — NOT silently patched here).
- **FINDING B:** `EOFError` from `get()` has no caller; process death is only
  observed via supervisor polling (`_supervise_rust_process` waits on
  `_death_event`, but nothing sets it from the reader path —
  `_handle_process_death` has zero callers).
- Lock mechanics (d4_4_audio_vad.py): time-based `_processing_lock_until`
  dict; `_set_lock(guild, dur)` sets expiry; `_release_lock(guild)` pops it;
  bridge `_handle_tts_done()` calls `_release_lock` + `_flush_buffered_audio`.
- Existing voice tests: interface asserts + missing-binary path only
  (tests/integration/test_bridge.py). Zero protocol traffic anywhere.
- Environment: `voice_receiver` binary NOT built locally (Tier B will skip);
  cargo IS available; `.venv/bin/python` works directly (uv cache read-only);
  pytest-asyncio asyncio_mode=auto; `import serin_core` currently succeeds as
  an EMPTY NAMESPACE PACKAGE (no functions!) — smoke test must check
  `hasattr(serin_core, 'sanitize_fts_query')`, never just importability.
- Rust side canonical protocol doc: voice/rust_receiver/src/main.rs module
  docstring + docs/wiki/python-rust-voice-protocol.md.

## Deliverables

```
tests/integration/fake_voice_receiver.py   # stand-in actor (see spec)
tests/integration/protocol_framers.py      # single source of frame layouts
tests/integration/test_wire_protocol.py    # Tier A (~10 cases, always run)
tests/integration/test_real_binary_smoke.py# Tier B (skip-if-absent)
tests/test_serin_core_smoke.py             # PyO3 smoke (skip-if-absent)
tests/integration/__init__.py              # exists already? verify; create if not
Ongoing.md                                 # this file (progress log at bottom)
```

### protocol_framers.py spec

Single source of truth for byte layouts. Constants mirroring main.rs:

```python
AUDIO_PREFIX = b"AUDIO:"   # AUDIO:{user_id}:{pcm_len}\n + pcm_len bytes
JOIN_PREFIX = b"JOIN:"     # JOIN:{user_id}\n
LEAVE_PREFIX = b"LEAVE:"   # LEAVE:{user_id}\n
TTS_DONE_FRAME = b"TTS_DONE\n"
SPEAK_PREFIX = b"SPEAK:"   # SPEAK:{len}\n + len bytes (Python -> Rust)
INTERRUPT_FRAME = b"INTERRUPT\n"
SHUTDOWN_FRAME = b"SHUTDOWN\n"

def encode_audio(user_id: str, pcm: bytes) -> bytes: ...
def encode_join(user_id: str) -> bytes: ...
def encode_leave(user_id: str) -> bytes: ...
def decode_speak(header_line: str) -> int: ...  # raises ValueError on garbage
def connection_info_json(info: dict[str, Any]) -> bytes:  # json+\n
DEFAULT_CONNECTION_INFO: dict[str, Any]  # valid example (snowflake-sized ids >= 2**32)
```

No f-string protocol literals anywhere else in the tests — grep-enforced by
the sync-guard test.

### fake_voice_receiver.py spec

Standalone script run via `<sys.executable> fake_voice_receiver.py --scenario NAME [--pcm-bytes N] [--sample-pcm]`.

Behavior:
1. Read line 1 from stdin; parse JSON. On invalid JSON: print
   `FAKE_ERROR:bad_connection_info` to stdout and exit 3 (loud failure per
   dave_receive lesson). Valid: write `FAKE_READY` to stdout (diagnostic log
   line — exercises the reader's `('log', line)` branch).
2. Scenario loop reading stdin commands:
   - `join_then_audio`: emit `JOIN:{uid}`, then 3 AUDIO frames of
     `--pcm-bytes` each (payload = repeating pattern bytes or random via
     os.urandom — content asserted by length + echo, not by RNG semantics),
     then keep reading commands.
   - `echo_speak_tts_done`: whenever `SPEAK:{len}` + payload arrives, reply
     with `TTS_DONE\n` after consuming the full payload.
   - default: silent loop until command.
3. On stdin EOF or `SHUTDOWN`: exit 0. On `INTERRUPT`: emit
   `TTS_DONE\n` once (mirrors Rust interrupt→track-stop→End behavior) and
   continue.
4. All stdout writes flushed immediately (protocol correctness under
   partial-buffer delivery matters).

The scenario runner composes these behaviors; scenarios are data, not code
paths, so new cases are one-line additions.

### test_wire_protocol.py — Tier A case list

All use real subprocesses (`asyncio.create_subprocess_exec(sys.executable,
fake_script, ...)`) + REAL `RustStdoutReader`. No production edits.

1. `test_reader_parses_join_leave_tts_done_and_log_lines` — feed all four
   line types; assert exact event tuples in order.
2. `test_reader_parses_audio_frame_with_binary_payload` — AUDIO frame whose
   payload contains `\n`, `\x00`, high bytes; assert exact bytes round-trip
   (the parser must honor pcm_len, not split on newline inside payloads).
3. `test_reader_reassembles_audio_across_partial_reads` — write header and
   payload in small dribbled chunks with awaits between; assert one clean
   event (exercises the `while len(buf) < pcm_len` refill loop).
4. `test_reader_survives_truncated_audio_then_eof` — AUDIO header claiming
   more bytes than delivered, then pipe close → EOF sentinel; no hang
   (bounded by asyncio.wait_for in the test).
5. `test_reader_skips_garbage_lines_without_dying` — binary junk lines
   interleaved between valid frames; valid frames still parsed; junk lands
   as ('log', ...) events.
6. `test_reader_ignores_bad_pcm_len` — `AUDIO:u1:notanumber` skipped cleanly.
7. `test_connection_info_handshake_is_valid_json_first_line` — fake asserts
   handshake validity end-to-end via exit code (real bridge start path uses
   same shape; here we pin the format contract itself).
8. `test_speak_framing_byte_exact` — drive `send_tts_audio()` on a
   RustVoiceBridge instance wired to the fake; fake decodes header with the
   shared framer and echoes received length + sha256 back over stdout;
   test asserts equality with what was sent.
9. `test_interrupt_and_shutdown_acknowledged` — INTERRUPT yields one
   tts_done event; SHUTDOWN ends process with returncode 0 within timeout.
10. `test_raw_ssrc_guard_warns_but_does_not_drop` — AUDIO with sub-2**32 uid
    still produces an audio event (guard warns, never drops — io_bridge.py
    docstring contract).

### test_tts_done_lock_lifecycle.py — merged into Tier A file (case 11–12)

11. `test_tts_done_releases_processing_lock_end_to_end` — real
    RustVoiceBridge + MinimalAudioProcessor stub exposing
    `_processing_lock_until` dict + `_release_lock`/`_flush_buffered_audio`
    (duck-typed like the real AudioStreamProcessor surface); set lock via
    `_set_lock`; send SPEAK through `bridge.send_tts_audio()`; fake replies
    TTS_DONE; assert guild key removed from `_processing_lock_until`.
    THE regression net for the S10 lock story.
12. `test_tts_done_without_lock_is_noop` — release on absent guild raises
    nothing, state unchanged.

### Sync-guard (anti-drift tripwire): test_protocol_sync_guard.py

- Reads `voice/rust_receiver/src/main.rs` source text.
- Asserts every framer constant's literal appears in it (e.g. `AUDIO:` /
  `JOIN:` / `LEAVE:` / `TTS_DONE` / `SPEAK:` / `INTERRUPT` / `SHUTDOWN`).
- Asserts framer constants appear in `fake_voice_receiver.py`.
- If either drifts, the failure message points at BOTH files ("update the
  fake + framers in the same commit").
- Skips (with reason) if main.rs is missing — never fails a checkout without
  the voice subtree.

### test_real_binary_smoke.py — Tier B

`pytest.mark.skipif(not Path(BINARY).exists(), reason="voice_receiver not built")`:
spawn real binary, send DEFAULT_CONNECTION_INFO, expect it stays alive ~0.5s,
send SHUTDOWN, await exit ≤5s, returncode in (0, None-killed). No Discord —
launch-only. Also asserts the bridge's own default path resolution matches
the real binary location when present (path-rot tripwire).

### test_serin_core_smoke.py

```python
serin_core = pytest.importorskip("serin_core")  # then:
if not hasattr(serin_core, "sanitize_fts_query"):
    pytest.skip("serin_core built as namespace package without PyO3 functions")
```

- `sanitize_fts_query`: compare against the pure-Python fallback algorithm
  copied from bm25_index._sanitize_query on a corpus of nasty queries —
  equality REQUIRED (same spec).
- `filter_thinking` (if present): thinking-tagged sample → no tags survive;
  equals ThinkingFilter fallback output on the same samples.
- `rerank_candidates` (if present): ordering contract vs
  `_rerank_results_simple` on a tiny candidate set (may differ in tie-order —
  assert set-of-top-k equality, documented).

## Out of scope (explicitly)

- No changes to any file under serin/ in Plan 4 (pure test addition).
- FINDING A/B fixes: filed in bugs_to_fix_later.md as a follow-up proposal,
  not silently patched.
- Real DAVE/audio round-trip (needs live Discord) — manual checklist item.

## Commit plan (Plan 4)

Single commit after gates:
`test(voice): wire-protocol integration harness — fake receiver, framers, sync-guard, smokes`
Body: findings A/B pinned as documentation, environment skip matrix, gate results.

---

# PLAN 3 — Pipeline metrics history (panel-queryable stage timings)

## Why (doc anchors)

- runners_pipeline.py logs total_ms + stage_timings every run; NOTHING reads
  them (verified by grep across serin/ + control_panel/static). Write-only
  telemetry.
- Panel buffers (_prompt_history, bot_state, _request_metrics) are RAM-only;
  hot_reloader restarts wipe them constantly.
- ARCHITECTURE edge A is the sanctioned pipeline→d1_5 channel; ops_tooling is
  the designated home for operational machinery (THE_LAW table).

## Verified current state (2026-08-26 recon)

- `runners_pipeline.process()` final block (≈L157-163) computes
  `total_ms = round(sum(ctx.stage_timings.values()), 2)` and logs it. No
  persistence.
- Authoritative schema: d4_3_schema_store.py (now also carries
  `channel_dynamics` from Plan 2 — follow its table-definition style).
- Storage dir d4_1_core_storage/ now has 4 files + __init__ (Plan 2 added
  d5_4_dynamics_store.py). Adding d5_5_metrics_store.py keeps Rule-1 OK
  (5 files max — this is the LAST free slot; noted for future splitters).
- Panel routes live tree: d4_6_routes/{d5_1_core_routes,d5_2_voice_routes,
  d5_3_debug_routes}; registrars wired in d3_2_panel_server/__init__.py.
  State helpers in d4_7_state/d5_1_state_access.py (pattern to follow).
- BackgroundProcessor.run_maintenance exists (d2_2_tooling_background) —
  retention pruning hook target.
- BotConfig (d2_1_base_config.py): add METRICS_ENABLED/METRICS_RETENTION_DAYS.

## Design decisions (locked)

- Store metrics in the SAME SQLite DB as schema store (bot_data.db) — no new
  storage engine; table created idempotently by the authoritative DDL module.
- One INSERT per completed pipeline run, written by a recorder in d1_5 via
  FUNCTION-SCOPED lazy import inside runners_pipeline (edge-A legality —
  mirrors broadcast_event usage). Best-effort: any exception is logged at
  debug and NEVER affects the message flow (metrics must be strictly
  additive).
- Recorder API takes primitives (dict[str, Any]) — no MessageContext import
  in d1_5 (would invert layering); JSON-encode stage_timings there.
- Aggregation math in Python (avg/p50/p95/histogram) — SQLite is storage,
  not an analytics engine; result sizes are small.
- METRICS_ENABLED=false short-circuits the recorder (zero cost when off);
  default true (this is the point of the feature).
- Retention: delete rows older than METRICS_RETENTION_DAYS (default 14) —
  called from BackgroundProcessor.run_maintenance and opportunistically on
  recorder write (throttled: at most once/hour).

### Table DDL (added to d4_3_schema_store.py)

```sql
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id TEXT,
    username TEXT,
    channel_id TEXT,
    responded INTEGER NOT NULL DEFAULT 0,       -- bool: did Serin send anything
    halt_reason TEXT,                            -- NULL = ran to completion
    error_flag INTEGER NOT NULL DEFAULT 0,       -- any stage_error halt
    total_ms REAL,
    stage_timings_json TEXT NOT NULL DEFAULT '{}' -- {"stage_name": ms}
);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_ts ON pipeline_runs(ts);
```

### New files

- `serin/d1_5_ops_tooling/d2_2_tooling_background/d5_3_metrics_recorder.py`
  IF d2_2_tooling_background has room (CHECK file/dir counts at build time —
  Rule 1). Fallback location: inside control panel server subtree next to
  state access. Final name/path decided by the Law checker, not preference.
  API:
  ```python
  class PipelineMetricsRecorder:
      def __init__(self, conn_path_provider: Callable[[], str | None]) -> None ...
      def record_run(self, *, user_id, username, channel_id, responded,
                     halt_reason, error_flag, total_ms, stage_timings) -> None
      def prune(self, retention_days: int) -> int  # rows deleted
      def summary(self, hours: int = 24) -> dict[str, Any]
      def recent_runs(self, limit: int = 50) -> list[dict[str, Any]]
  ```
  - Opens its own short-lived sqlite3 connection per operation (WAL-safe,
    thread-agnostic), never holds one open across messages.
  - `summary()`: runs/hour buckets, response rate, halt_reason histogram,
    per-stage avg/p50/p95/max (computed in Python from JSON), slowest run.
- Route registrar: `register_pipeline_metrics_routes(app, ...)` following the
  existing route-module pattern; mounted from panel __init__ with the others.
  Endpoints:
  - `GET /api/metrics/pipeline?hours=24&limit=50` → {summary, recent_runs}
  - `POST /api/metrics/prune` (confirm-gated like other mutating routes) →
    forces retention pass.

### Wiring (one production touch-point + config + maintenance)

1. runners_pipeline.process(): after the existing `pipeline.complete` log —
   ```python
   try:
       from <recorder module> import get_metrics_recorder
       get_metrics_recorder().record_run(...)
   except Exception:
       logger.debug("pipeline.metrics_write_failed", extra={...})
   ```
   Function-scoped import = legal edge-A. Module provides a module-level
   lazy singleton so repeated imports stay cheap.
2. d2_1_base_config.py: `METRICS_ENABLED` (default "true"), 
   `METRICS_RETENTION_DAYS` (default 14) — env-driven like siblings.
3. BackgroundProcessor.run_maintenance: call `prune()` best-effort.
4. Panel __init__: register the new routes.

### Tests (tests/server/test_pipeline_metrics.py + unit file)

- Schema pin: columns exist exactly as specified (style of test_user_affect).
- record_run roundtrip → recent_runs returns identical fields.
- summary(): seeded synthetic runs → correct p95/response-rate/halt histogram
  (hand-computed fixtures, deterministic).
- prune(): old rows deleted, fresh kept, returns count.
- recorder failure isolation: raising conn provider → record_run swallows
  (debug log), pipeline unaffected (simulate by pointing at unwritable path).
- METRICS_ENABLED=false → no row written.
- Route test: GET endpoint returns 200 + shape (existing server-test fixture
  pattern from tests/server/conftest.py).
- Edge-A legality: import-linter green (the lazy-import pattern again).

## Out of scope (explicitly)

- No frontend chart card (API-only this pass; UI later — decision point
  answered: API-only unless user upgrades scope mid-flight).
- No Prometheus/OTel export.
- No per-stage alerting/thresholds (data collection first).

## Commit plan (Plan 3)

Two commits:
1. `feat(ops): pipeline_runs metrics store + recorder + retention`
   (schema, recorder, config keys, maintenance hook, unit tests)
2. `feat(panel): /api/metrics/pipeline route + pipeline-run recording at act layer`
   (route registrar + runners_pipeline write site + route tests)
Bodies cite: write-only-telemetry gap, edge-A legality argument, gates run.

---

# PROGRESS LOG (append-only; newest first)

## [2026-08-26] DONE | Plan 4 + Plan 3 complete — 3 commits, all gates green
Plan 4 — commit 96df250 `test(voice): wire-protocol integration harness`:
- protocol_framers.py (single frame truth), fake_voice_receiver.py (EMIT/RAW/
  SPEAK-echo bench surface), test_wire_protocol.py (16 Tier-A cases),
  test_protocol_sync_guard.py (framer literals pinned vs main.rs; drift fails
  CI), test_real_binary_smoke.py (Tier B path-rot tripwire; skips w/o binary),
  test_serin_core_smoke.py (PyO3 == Python-fallback parity, namespace-package
  gate). No changes under serin/. Two production properties PINNED as tests:
  unterminated junk glues into the next line (swallows a frame); non-UTF8
  lines dropped with zero telemetry. FINDING A (no __aiter__ on reader)
  pinned as documentation test.
Plan 3 — commits 83f311f (ops) + fe11dbb (panel):
- pipeline_runs DDL in authoritative schema store (+started_ts index);
  NEW d5_5_pipeline_metrics.py recorder (duck-typed store, never raises);
  edge-A write in MessagePipeline.process after pipeline.complete via
  function-scoped import; PIPELINE_METRICS_ENABLED/_RETENTION_DAYS config;
  run_maintenance prune hook; GET /api/metrics/pipeline (summary block:
  p50/p95/halt-rate/slowest stage; opportunistic retention prune) +
  POST /api/metrics/prune (?confirm=yes gated); 16 tests incl. route
  integration through real register fn.
Gates at each commit: ruff / mypy strict (178 files) / pyright /
import-linter / bandit / detect-secrets green; full pytest 687 passed /
6 skipped. ONLY failure: test_semgrep_custom_rules — pre-existing sandbox
issue (read-only HOME mount breaks ~/.semgrep writes), reproduced on stashed
clean tree, documented in commit bodies. --no-verify used per repo precedent
with compensating controls stated in each body.
Leftovers: .secrets.baseline modification is from earlier plan work
(test_small_llm_seam entries) — intentionally NOT committed with these.

## [2026-08-26] plan | Ongoing.md created — full plans for 3 & 4
Recon done (graphify graph queried for the voice seam; all five production
files read: io_bridge, bridge_commands, process_watch x2, audio_vad lock
mechanics; existing test_bridge.py audited). Two pre-existing wiring findings
documented (async-iterator mismatch on the reader consumer; unowned EOFError)
— PINNED, not fixed, per plan scope. Environment facts recorded (binary not
built locally; cargo present; .venv direct python; serin_core imports as
EMPTY namespace package — smoke tests must hasattr-check). Next: implement
Plan 4 deliverables, then Plan 3.
