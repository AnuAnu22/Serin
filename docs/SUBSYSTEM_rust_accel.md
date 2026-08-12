# SUBSYSTEM: rust_accel — fast Rust escape hatches (serin_core PyO3 + voice_receiver subprocess + scanner)

Checklist: 4/4 files read (PLAN said 4 — confirmed exactly 4, plus vendored songbird documented as vendored). Status: DRAFT (wip).
Finalize name: `SUBSYSTEM_rust_accel.md`.

Root: `serin_core/`, `voice/rust_receiver/`, `scripts/undef-var-scanner/` (own Rust crates — NOT under `serin/` Python tree).

## Scope & role in the system

This subsystem is the set of **Rust binaries backed by native code** that accelerate or replace Python hot loops. There are **three unrelated Rust crates**: they only share the "written in Rust" property, not a common runtime or protocol.

1. **`serin_core`** — a **PyO3 extension module** (`.so` imported as `import serin_core` from Python). Replaces Python hot loops with compiled regex + zero-allocation string passes: FTS5 query sanitization, thinking-tag filtering, natural-language contractions, and BM25 rerank.
2. **`voice_receiver` (+ `minimal_test`)** — a **standalone songbird voice binary** spawned as a *subprocess* by the Python `RustVoiceBridge` (Subsystem 10). This is CONNECTIONS J's Rust half: it owns all Discord voice UDP decode + TTS playback over stdin/stdout.
3. **`undef-var-scanner`** — a **dev/CI static-analysis CLI** that scans Python files for `{undefined_var}` braces inside constant strings. Not part of runtime.

**graphify is BLIND to all three** (Rust AST not captured). Everything here was read directly from `.rs` sources and cross-checked against the Python seams.

## The PyO3 seam (serin_core)

`serin_core/src/lib.rs` (385 lines) is a `#[pymodule]` exporting **9 functions**, all pure functions with no state and no I/O:

| Rust function | Python import site | What it accelerates |
|---|---|---|
| `sanitize_fts_query` | `d6_1_bm25_index.py:46` | single-pass FTS5 special-char stripping |
| `filter_thinking` | `d6_1_thinking_filter.py:70` (importlib) | 13 compiled regex patterns stripping LLM thinking tags |
| `apply_contractions` | `d3_3_response_generator.py:352-354` | one-pass N=50 contraction replacement |
| `rerank_candidates` | `d5_1_search_store.py:168` | score + recency-decay combined rerank |
| `validate_json_fast` | (not matched to live importer) | fast JSON validity check |
| `compute_text_similarity` | (not matched to live importer) | Levenshtein normalized 0..1 |
| `extract_mentions` | (not matched to live importer) | `<@...> / <@&...> / <#...>` extraction |
| `tokenize_words` | (not matched to live importer) | whitespace word split |
| `sanitize_markdown` | (not matched to live importer) | strips `**bold**`, ```code```, `~~strike~~`, etc. |

**Key architectural fact: serin_core is an OPTIONAL accelerator, not a hard dependency.** Every one of the 4 live import sites wraps the `import serin_core` in try/except and falls back to the pure-Python equivalent (e.g. `bm25_index` has a Python fallback loop, `search_store` falls back to `_rerank_results_simple`, `response_generator` / `thinking_filter` have Python regex fallbacks). So the bot runs correctly with the `.so` absent; Rust is a speed layer only.

Patterns worth noting in lib.rs:
- **13 compiled thinking patterns** (LazyLock<Vec<Regex>>): `<|channel|>thought`, `thinking...response`, `<reasoning>`, `<<<thinking>>>`, `/think`, `[Thinking]`, `<!-- thinking -->`, `<tool_call>`, `<|reserved_special_token_N|>`, `[think]`, `BEGIN_THINKING`, and `<｜begin▁of▁thinking｜>` (the Anthropic-style Tibetan-bookmark tokens). The last two (BEGIN_THINKING, `<｜begin▁of▁thinking｜>`) document models newer than the dated prose in some docs.
- **50 contractions** in a `(?i)\b(...)\b` combined regex, sorted longest-first, with first-letter capitalization preservation.
- `rerank_candidates`: `0.7*norm_score + 0.3*recency`, recency = exponential decay with **half-life ~30 days** (`-age/30/ln30`).
- `filter_thinking` compiles **13 patterns** and applies all with `replace_all → ""` then `.trim()`.
- Unicode-aware throughout (`.chars()`, not `.as_bytes()` — correct for combining marks in mentions), except the raw-PCM `from_raw_parts` broadcast in voice_receiver (intentional, that's PCM not text).

Caveat: `validate_json_fast`, `compute_text_similarity`, `extract_mentions`, `tokenize_words`, `sanitize_markdown` are **registered and implemented but no live Python importer calls them** — they are either evans peeled dead Rust or reserved for future use (Phase-4 note: a Python-wide search found no `serin_core.validate_json_fast` etc. callers).

## The voice subprocess seam (voice_receiver) — CONNECTIONS J Rust half

`voice/rust_receiver/` is a **separate crate** (`serin-voice-receiver` v3.0.0) with two `[[bin]]` targets: `voice_receiver` (`src/main.rs`, 582 lines, production) and `minimal_test` (`src/minimal_test.rs`, 87 lines, diagnostic).

### vendor/songbird — VENDORED dependency (documented, not file-by-file)

`voice/rust_receiver/vendor/songbird/` is a **vendored copy of the songbird 0.6.0 crate**, pinned via `Cargo.toml` `[patch.crates-io] songbird = { path = "vendor/songbird" }`. Per the Cargo.toml HISTORY CORRECTION (2026-08-05): the original DAVE tail-offset bug (Opus InvalidPacket on every decode) is **already fixed in upstream 0.6.0** (commit 653177e7, 2026-03-12) — that part is a no-op. The vendored tree exists for **ONE behavioral patch: ClientConnect SSRC mapping** (`ws.rs` + `events/core.rs` + `events/context/mod.rs`). Upstream ignores ClientConnect as "discontinued," but Discord still sends it and the DAVE decrypt path silently drops packets from unmapped SSRCs. See `docs/wiki/songbird-clientconnect-patch.md`. Documented as vendored; not walked file-by-file.

### The wire protocol (main.rs ↔ Python)

No gateway client is used — the Rust `songbird::driver::Driver` connects directly to Discord's voice UDP endpoint (avoids the dual-gateway conflict with py-cord, per CONNECTIONS J). Protocol is newline-delimited on stdin/stdout:

**stdin (Python → Rust):**
- `ConnectionInfo` JSON (single line, read first): `{endpoint, token, session_id, guild_id, channel_id, user_id}`
- `SPEAK:{len}\n` + `len` bytes of **WAV** → plays through the voice channel
- `INTERRUPT\n` → `current_handle.stop()` immediately
- `SHUTDOWN\n` → clean exit (also fires on stdin EOF)

**stdout (Rust → Python):**
- `AUDIO:{user_id}:{pcm_len}\n` + `pcm_len` raw **48kHz stereo i16 PCM** bytes (per 20ms VoiceTick / 50fps, per speaking user)
- `JOIN:{uid}\n` / `LEAVE:{uid}\n` — derived from SSRC→user_id mapping + active-set diffing
- `TTS_DONE\n` — fires on `TrackEvent::End` via the one-shot `TtsDoneNotifier`; signals Python to release the per-guild processing lock (Subsystem 10).

**Architecture inside main.rs:**
- `Receiver` (DashMap `known_ssrcs: u32→user_id`, `active_users`) registered as global handler for `SpeakingStateUpdate`, `VoiceTick`, `ClientDisconnect`. SSRC→UID learned from SpeakingStateUpdate + ClientConnect; VoiceTick gives decoded PCM indexed by SSRC.
- events → flume::unbounded → main loop → stdout; main loop @ ~20Hz (50ms sleep), drains stdout events first, then an mpsc stdin channel.
- TTS playback: Python sends WAV → written to `/tmp/serin_tts_output.wav` → `driver.play_input(File::new(...))` → `TtsDoneNotifier` attached for `TrackEvent::End`.
- **Safety note:** the PCM `from_raw_parts` at :211 is `unsafe` but justified (songbird hands `&[i16]`, reinterpreting to bytes for transport). Documented in-source.

### minimal_test.rs — diagnostic binary

A 30-second-idle smoke test that spawns only a `Driver` (DecodeMode::**Decrypt**, no decode) and connects — to bisect whether a voice crash is in songbird's driver init vs. our event handlers (per its header comment). Build target `minimal_test`, **not used at runtime**.

## The static-analysis binary (undef-var-scanner)

`scripts/undef-var-scanner/src/main.rs` (265 lines) — standalone CLI: `undef-var-scanner <directory> [--exclude pat]`. Walks `.py` files (skips `__init__.py`/`__main__.py`/`__pycache__`/`.venv`/`target`/`.git`/`node_modules`) and flags `{identifier}` inside **non-f-string constant strings** where the identifier isn't a def/class/import/assignment in the file. Skips docstrings and SQL keywords. Exit 0 = clean, 1 = issues found (printed to stderr). **Dev/CI tooling only; zero runtime importers.** It's the honest-detection counterpart to the codebase's `{var}` placeholder strings.

## Cross-cutting / notable findings (see CONNECTIONS.md)

1. **Three separate Rust crates, three distinct roles** — PyO3 module (in-process, optional accelerator), subprocess voice binary (mandatory for voice, owned by Subsystem 10), and a CLI lint tool (dev-only). They are *not* one system.
2. **serin_core is speed-only, not correctness-critical** — all 4 live PyO3 call sites fall back to Python on ImportError/AttributeError. The bot's text correctness does not depend on Rust.
3. **CONNECTIONS J confirmed end-to-end** — `main.rs` wire protocol matches the `RustVoiceBridge.start()` (d5_1_process_watch:116-180) spawn + `RustStdoutReader` (`d4_1_io_bridge`) parse. The `TTS_DONE` handshake is the lock-release signal documented in Subsystem 10.
4. **`RUST_VOICE_RECEIVER_PATH` config is dead + stale** (config_base:66-68): set from env, default path is wrong (`serin/d1_4_config_base/voice/...`), and **no code reads it**. `RustVoiceBridge` computes the correct binary path itself (`os.pardir`×4 from process_watch dir → `voice/rust_receiver/target/release/voice_receiver`), independent of the config. Confirms the Subsystem-1 stale finding. Phase-4 candidate: delete the config key or wire it in.
5. **Vendored songbird 0.6.0** with a single behavioral patch (ClientConnect SSRC mapping) — the DAVE tail-offset fix is already in upstream, so the vendor tree is *thin* (one patch), tracked via `[patch.crates-io]` + `docs/wiki/songbird-clientconnect-patch.md`.
6. **Newer model tokens documented in rust regexes** (`BEGIN_THINKING`, `|begin▁of▁thinking|`) not mentioned in older Python docs — the thinking filter is kept current here.

## What's NOT here
- The Python half of the voice bridge (Subsystem 10: `d3_2_bridge_io/`, `AudioStreamProcessor`, `d4_1_io_bridge` `RustStdoutReader`) — this subsystem only owns the Rust `.rs` files; the Python consumers live under `serin/d1_2_gateway_io/`.
- Hot-reload build orchestration (`d2_3_hot_reloader.py` runs `cargo build` for voice_receiver + `maturin develop` for serin_core — Subsystem 12) — separate.
- Any `target/` build artifacts (not documented; build outputs).