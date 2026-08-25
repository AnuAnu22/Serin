# Bugs to Fix Later

Generated from a static-analysis + test sweep run on the working tree
(after the `bot_opinions` wiring work). Scanners used: `ruff`, `mypy`,
`pyright`, `semgrep`, `bandit`, `vulture`, and the full `pytest` suite.

## Scope & honesty note

- The `bot_opinions` wiring changes introduce **0 new errors**: pyright on the
  four touched files went from 10 (baseline) → 4 pre-existing errors, ruff is
  clean, mypy is clean, semgrep is clean (0 findings), bandit is clean.
- The numbers below are the **pre-existing** project-wide debt, curated into
  what is genuinely actionable vs. noise. The ~603 pyright errors are
  overwhelmingly the strict-mode `Any`-cascade (`reportUnknownMemberType` /
  `reportUnknownVariableType` / `reportUnknownArgumentType`) caused by untyped
  `ctx.*` fields and `Any`-typed dependencies — a typing-debt category, not
  individual logic bugs. Those are summarized at the end, not enumerated 1-by-1.

## Scan summary

| Scanner | Result | Notes |
|---|---|---|
| ruff | ✅ clean | no findings |
| mypy (strict) | ✅ clean | no issues in `serin/` |
| pyright (strict) | ⚠️ 603 errors | all pre-existing; ~295 are non-`Any`-cascade (private-usage, unused helpers, missing stubs, constant-redefinition); rest is `Any`-cascade |
| semgrep (`.semgrep/rules`) | ✅ 0 findings | 5 custom rules, 195 files |
| bandit | ✅ clean | only `#nosec` skips (5), no real issues |
| vulture (≥80% conf) | ⚠️ 4 findings | dead/unused variables (see below) |
| pytest | ⚠️ 2 failed, 627 passed | 1 real flake + 1 environment-only |

---

## A. Real bugs / latent risks (prioritized)

### A1. `affect_engine.py:114` — `asyncio.get_event_loop()` causes order-dependent test failure
- **Symptom:** `tests/test_affect_engine.py::test_snapshot_cached_returns_neutral_on_miss`
  passes in isolation (20/20) but **fails in the full suite**. pyright emits
  `DeprecationWarning: There is no current event loop` at that line.
- **Root cause:** `asyncio.get_event_loop()` is deprecated and returns/creates
  different loops depending on prior test event-loop state (pytest-asyncio
  manages loops per-test). `snapshot_cached` likely calls it lazily.
- **Risk:** Flaky behavior; could also affect runtime if a loop isn't set.
- **Fix:** Replace `asyncio.get_event_loop()` with `asyncio.get_running_loop()`
  (inside a coroutine) or `asyncio.new_event_loop()` guarded by
  `asyncio.get_event_loop_policy().get_event_loop()` only when needed. Prefer
  passing the loop in explicitly.

### A2. `d4_2_connection_store.py:56` — `None` membership test
- **Code:** `if config.QDRANT_DOCKER_CONTAINER_NAME in c.name:` where pyright
  reports `c.name` is `str | None`.
- **Risk:** If a container's `name` is `None`, `x in None` raises `TypeError`
  at runtime (docker SDK can return `None` for unnamed containers).
- **Fix:** `if c.name and config.QDRANT_DOCKER_CONTAINER_NAME in c.name:` (or
  `c.name or ""`).

### A3. `d4_3_memory_write.py:238` — `self.client.user.id` optional access
- **Code:** `bot_user_id = str(self.client.user.id)` inside a `try/except`.
- **Risk:** pyright flags `"user" is not a known attribute of "None"` — if
  `self.client`/`client.user` is `None` the `except` swallows it and falls back
  to `"serin"`, so it's **safe at runtime** but the bare `except Exception:`
  hides the real cause and the type is wrong.
- **Fix:** Narrow the type (`client: discord.Client | None`) and check
  `self.client and self.client.user` before access; avoid bare `except`.

### A4. `d4_2_sync_crawler.py:182-220` — `TextChannel` attribute access flagged
- **Errors:** `Cannot access attribute "history"/"id"/"name" for class
  "TextChannel"` plus `Argument of type "TextChannel" cannot be assigned to
  parameter "channel" of type "TextChannel"` (same-name, different module path).
- **Likely cause:** `discord.py` stub-version skew — the code annotates
  `discord.channel.TextChannel` but pyright resolves `discord.TextChannel` from
  a different stub path. The attributes (`history`, `id`, `name`) exist at
  runtime, so this is probably a **typing/annotation mismatch, not a runtime
  bug** — but it should be confirmed against the installed `discord.py` version.
- **Fix:** Standardize the `TextChannel` import path across the file, or add a
  pyright `reportAttributeAccessIssue = false` suppression scoped to this module
  if it's a known stub limitation.

### A5. Missing type stubs for `nltk.sentiment` / `vaderSentiment` (runtime import risk)
- **Errors:** `d4_3_memory_write.py:52` (nltk), `d4_4_core_manager.py:18`
  (vaderSentiment) — `Stub file not found ... (reportMissingTypeStubs)`.
- **Risk:** Usually harmless (pyright only), BUT if these packages are not
  installed at runtime, the `import` fails. Confirm they are in
  `requirements.txt`/`pyproject` and pinned. (Per `pyrightconfig.json`,
  `reportMissingTypeStubs = false`, so these are only visible because the
  strict include re-enables them — see category C.)

---

## B. Dead code / unused (vulture ≥80%)

| File | Line | Finding | Action |
|---|---|---|---|
| `serin/d1_5_ops_tooling/d2_1_control_panel/d3_4_panel_routes.py` | 49 | unused variable `broadcast_func` | remove or wire up |
| `tests/server/conftest.py` | 62 | unused variable `bot_state_dict` | remove |
| `tests/test_background_impressions.py` | 18 | unused variable `order_by` | remove |
| `tests/test_background_impressions.py` | 75 | unused variable `store_arg` | remove |

---

## C. Project-wide typing debt (pyright strict) — summary, not enumerated

These are consistent patterns across many files. They do **not** block CI today
(`pyrightconfig.json` sets `reportMissingTypeStubs = false`; some are re-shown
because the strict include widens checks). Fix opportunistically:

- **`Any`-cascade (majority of 603):** untyped `MessageContext` fields and
  `Any`-typed dependencies (`ctx.beliefs`, `memory_system`, `personality`,
  `affect_engine`) cause `reportUnknownMemberType`/`VariableType`/`ArgumentType`.
  *Fix:* annotate the dynamic `ctx` fields or narrow the `Any` params.
- **`reportPrivateUsage` (protected/private across modules):** many `_name`
  helpers/fields used outside their declaring module (e.g. `_affect_context`,
  `_belief_evolution_context` imported in `d5_1_prompt_assembly.py`; `_guild_id`,
  `_restart_timestamps`, `_stderr_buf`, `_death_event`, `_reconnect_callback` in
  `d4_3_bridge_recovery.py`; `_build_qdrant_filter`, `_update_ingestion_stats`).
  *Fix:* drop the leading underscore or add an explicit re-export.
- **`reportUnusedFunction`:** several `_`-prefixed helpers defined but never
  called (`_time_label`, `_confidence_label`, `_fuzz_memories`, `_affect_context`,
  `_belief_evolution_context`, `_facts_context`, `_truncate_to_budget`,
  `_build_qdrant_filter`, `_update_ingestion_stats`). *Fix:* verify they are
  re-exported intentionally; if not, remove.
- **`reportConstantRedefinition`:** `QDRANT_AVAILABLE`, `EMBEDDING_AVAILABLE`
  redefined in `d4_2_connection_store.py` / `d4_4_core_store.py`. *Fix:* guard
  with `if not typing.TYPE_CHECKING` or compute once at module top.
- **`reportInvalidTypeForm`:** `d3_2_discord_bot.py` — `Variable not allowed in
  type expression` (likely `tuple[X, ...]` with a runtime var). *Fix:* use
  `tuple[...]` with concrete types or `Sequence[...]`.
- **"object is not awaitable"** (`d4_1_panel_control.py`) and **"Except clause
  is unreachable"** (`d3_4_sync_monitor.py:130`) — verify control flow.

---

## D. Environment-only (NOT a code bug)

- `tests/test_static_analysis.py::test_semgrep_custom_rules` failed **only**
  because the sandbox has a read-only `/home/user3/.semgrep` (semgrep crashes on
  `mkstemp` writing its settings file). When run with a writable `HOME`,
  `semgrep --config .semgrep/rules/` returns **0 findings**. The test itself is
  fine; it needs a writable settings dir in CI. Add `SEMGREP_SETTINGS_DIR` or a
  writable `$HOME` in the CI runner.
- `vulture` and `semgrep` are not installed in the default `.venv` resolution
  path here; installed ad-hoc for this sweep. Add them to the dev dependency set
  if CI runs them.

---

## Recommended next steps (in order)

1. **A2** (`None` membership in `connection_store.py`) — smallest, real
   runtime-crash risk. Quick fix.
2. **A1** (`get_event_loop` flake) — fix to remove the full-suite test flake.
3. **A4** — confirm against installed `discord.py` version; align import path.
4. **A3 / A5** — narrow `Optional`/missing-stub imports.
5. **B** — delete the 4 unused vars.
6. **C** — schedule typing-debt cleanup as a separate refactor PR (large,
   low-risk-per-item).
