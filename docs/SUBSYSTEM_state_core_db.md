# SUBSYSTEM: state_core_db — d1_3_state_core (db_protect + core_memory + model_system)

Checklist: 20/20 files read. Status: DRAFT (wip). Finalize name: `SUBSYSTEM_state_core_db.md`.

Paths under `serin/d1_3_state_core/`.

## Scope & role in the system

`d1_3_state_core` is a *capability* subsystem — it does NOT run a pipeline stage. It
supplies shared, generally-imported infrastructure used by the d1_1 pipeline and d1_5 ops:

- **Database protection** (`d2_1_db_protect`) — SQLite integrity, backup, recovery, shutdown.
- **Core memory structures** (`d2_2_core_memory`) — the fact/belief stores, BM25 index, and a
  Qdrant-backed "memory system" wrapper.
- **Model abstraction** (`d2_3_model_system`) — the `ModelInterface` ABC + an OpenAI-compatible
  HTTP connector (llama-swap/vLLM/etc.) so the pipeline can swap backends without changing bot code.

Note this directory ONLY covers db_protect + core_memory + model_system. The other two
`d2_*` subdirs under `d1_3_state_core` — `d2_4_core_voice` and `d2_5_state_conversation` —
are documented as SEPARATE subsystems (state_core_voice, state_core_conversation).

## Files

### d2_1_db_protect (database protection)

- `d3_1_protect_backup.py` — **DatabaseProtectorBackup**. `create_backup()` wraps the SQLite DB
  in a gztar archive + writes `backup_info.json` metadata; rate-limited auto-backups; prunes to
  `max_backups=50`; extracts/validates metadata. The DB filename is hardcoded `serin.db`.
- `d3_2_protect_core.py` — **DatabaseProtectorCore**. Integrity checks (e.g. `PRAGMA
  integrity_check`), detects corruption. **STALE:** hardcodes `chroma_dir = data_dir/"chroma_data"`
  and refers to ChromaDB — the system uses Qdrant now. `required_tables` =
  `['users','relationships','recent_messages']` also lags the real schema. Exposes module-global
  lazy singleton via `get_database_protector()` (checked-instantiation pattern, conservative).
- `d3_3_protect_recovery.py` — **DatabaseProtectorRecovery**. SQLite export/import repair path;
  deletes the chroma dir; full backup restore with path-traversal-safe tar extraction.
- `d3_4_protect_shutdown.py` — **DatabaseProtectorShutdown** (subclasses core). Registers
  SIGINT/SIGTERM + `atexit` handlers, does a `pre_shutdown` backup before exit and exposes
  `get_health_status()`.
- `__init__.py` — re-exports `DatabaseProtector` (the shutdown subclass), the error classes, and
  `get_database_protector()`.

### d2_2_core_memory (fact / belief / memory structures)

- `d3_1_belief_store.py` — **BeliefStore**. State machine over beliefs (PENDING / SUPPORTED /
  CONTESTED / SUPERSEDED / UNKNOWN per the states used). `add_or_update_belief`,
  `infer_beliefs_from_facts`, `get_relevant_beliefs`. Confidence formula `0.3 + 0.7 * total_evidence /
  max(total,1)`; SQL UPDATE statements reference `last_contradicted_at` /
  `contradiction_resolved_at`. This is the LEGACY belief model.
- `d3_2_evidence_store.py` — **FactStore**. `add_fact`, `get_relevant_facts` (keyword-based LIKE
  scoring). **NOTE:** its `INSERT INTO facts` writes `(subject_id, subject_name, claim, category,
  belief, variance, log_odds, first_observed, last_confirmed, primary_source, source_type, state,
  claim_hash)` and `add_fact` does the auto-supersede (`UPDATE facts SET is_active = 0`). This is
  the NEWER Bayesian fact schema, NOT the legacy schema in `memory_store.py`.
- `d3_3_belief_dynamics.py` — **BayesianBeliefEngine**. The richest model: log-odds Bayesian
  updates, `SOURCE_WEIGHTS` per source-type tier, temporal decay (`HALF_LIFE_DAYS=30`),
  Kalman-influenced variance, `claim_hash` dedup, and a `fact_observations` ledger table.
  `observe()`, `store_fact()` (corroborates on duplicate claim_hash), `apply_temporal_decay()`.
  Namespace guard on whitelisted SQL columns. This is the ACTIVE/new belief engine.
- `d3_4_memory_store.py` — **QdrantMemorySystem**. I/O wrapper owning connections to Qdrant
  (vector) + SQLite (structured). Optional dialect detection (`QDRANT_AVAILABLE`,
  `EMBEDDING_AVAILABLE`, `BM25_AVAILABLE` all degrade to None on missing deps). Owns the SQLite
  schema init (`_init_sqlite_schema`), WAL pragmas, corruption self-heal. **STALE:** the
  `facts`/`beliefs` tables created here (lines ~288-356) use a LEGACY schema
  `(id, content, category, confidence, source_message_id, ..., superseded_by, is_active)` that does
  NOT match the schema the FactStore / BayesianBeliefEngine actually write to. Instantiates
  `self.fact_store = FactStore(self.conn)` and `self.belief_store = BeliefStore(self.conn)`.
- `d3_5_memory_helpers/__init__.py` — empty (namespace marker).
- `d3_5_memory_helpers/d6_1_bm25_index.py` — **SQLiteBM25Index**. SQLite FTS5 BM25 keyword search
  over `documents_fts`. **PyO3 seam:** `_sanitize_query()` at line ~43 dyna-imports
  `serin_core.sanitize_fts_query`, falling back to a Python special-char scrubber when the Rust
  module is unavailable. `search()` builds the WHERE clause from fixed string fragments only (SQLi
  -safe), scores with `bm25(documents_fts)`.
- `__init__.py` — empty.

### d2_3_model_system (model abstraction / LLM connector)

- `d3_4_system_interface.py` — **ModelInterface (ABC)**. The swap contract: `load_model`,
  `is_connected` property, async `chat_completion` / `send_input`, sync `blocking_*` defaults
  (raise `NotImplementedError` unless overridden), `get_model_info`. Docstring lists intended
  backends: LM Studio, vLLM, Safetensors, OpenAI.
- `d3_2_system_connector.py` — **LLMConnector(ModelInterface)**. OpenAI-compatible HTTP connector
  (works with llama-swap/vLLM/etc.). Reads all `LLM_*` settings from `config` (d1_4). `_try_connect`
  detects the model server's available models and auto-selects; `_retry_loop` runs a daemon thread
  that reconnects every `RETRY_INTERVAL=15`s until `_connected`. Uses the `openai` SDK pointed at
  the custom `base_url`. For gemma/deepseek it injects `chat_template_kwargs.enable_thinking` via
  `extra_body`.
- `d3_1_system_adapter.py` — **ModelAdapter** + **ModelDetector**. Detects model family from the
  model name (`qwen/deepseek/gemma/phi/mistral/gpt/claude/llama`); holds per-family
  `MODEL_CONFIG` (stop tokens, strip tokens, thinking patterns). `clean_response()` strips tokens,
  thinking tags, `Name:` prefixes, whitespace. `format_messages()` is a passthrough (OpenAI-compatible
  servers do their own formatting).
- `d3_3_system_factory.py` — model registry/factory. Module-global `loaded_models` dict;
  `get_model_connector()` caches by model_name; `load_model_if_needed()` calls `load_model()` if
  temp/top_p given; `unload_model()` / `unload_all_models()` tear down connectors. `get_available_providers()`
  always returns just `llama-swap`. graphify shows this factory is called by `d4_1_state_access.py`
  (d1_1 wiring) and `d5_2_tooling_background_summary.py` (d1_5).
- `d3_5_model_helpers/__init__.py` — empty exposing the filter (imports analyzed).
- `d3_5_model_helpers/d6_1_thinking_filter.py` — **ThinkingFilter**. Strips reasoning/thinking tags
  (gemma `<|channel|>thought...`, XML `<thinking>`, markdown `[Thinking:...]`, parens, special
  tokens). **PyO3 seam:** `filter()` at line ~70 uses `importlib.import_module("serin_core")` →
  `serin_core.filter_thinking`, falling back to the compiled Python regex list. Also exposes
  `has_thinking_tags()`, `extract_thinking()`, and a `get_thinking_filter()` lazy singleton +
  `filter_thinking()` / `filter_for_memory()` convenience wrappers.
- `__init__.py` — empty.

### d1_3_state_core/__init__.py

Empty (directory namespace). No re-exports.

## Cross-cutting / notable findings (see CONNECTIONS.md)

1. **Two divergent fact/belief schemas.** The ACTIVE stores (`FactStore`,
   `BayesianBeliefEngine`) read/write a Bayesian facts schema — `subject_id, claim, belief,
   variance, log_odds, ..., claim_hash` — and a `fact_observations` ledger. But the sole schema
   creator inside this subsystem (`QdrantMemorySystem._init_sqlite_schema`) still emits a LEGACY
   `facts(id, content, category, confidence, source_message_id, ...)` / `beliefs(id, ..., state,
   last_contradicted_at, ...)`. The matching AUTHORITATIVE schema lives in
   `d1_1_pipeline_flow/.../remember_core/d4_3_schema_store.py` (d1_1, Subsystem 5). **Cross-subsystem
   dependency:** this subsystem's stores depend on a schema built by the pipeline subsystem, and
   `memory_store.py` builds a stale one that FactStore won't match. Needs Phase-4 verification of
   whether `schema_store` runs before any read/write and whether the legacy CREATE TABLE in
   `memory_store` is dead/conflicting.
2. **Two belief engines coexist:** legacy `BeliefStore`/`FactStore` (keyword scoring, string state
   machine) vs active `BayesianBeliefEngine` (log-odds, variance, temporal decay, claim_hash dedup).
   Pipeline `d4_4_core_store.py` wires BOTH (imports BeliefStore, FactStore, BayesianBeliefEngine;
   sets `belief_engine = BayesianBeliefEngine(self.conn)`). `perception_classify.py` (d1_1) also
   reaches in for the engine lazily. Worth explicitly mapping which writes go where in Phase 4.
3. **PyO3 seams (graphify BLIND — both confirmed by grep):**
   - `d6_1_bm25_index.py:46` → `serin_core.sanitize_fts_query`
   - `d6_1_thinking_filter.py:70` → `serin_core.filter_thinking`
   Both fall back to Python when `serin_core` is unimportable.
4. **Model backends are decoupled** via `ModelInterface` ABC; only `LLMConnector`
   (llama-swap/OpenAI-compatible) ships. `get_available_providers()` hardcodes `llama-swap`.
   `enable_thinking` is passed through only for gemma/deepseek via extra_body.
5. `db_protect` is STALE about storage tech: references ChromaDB/chroma_data and legacy
   `required_tables` (users/relationships/recent_messages). The pipeline's `d4_3_schema_store.py`
   owns the real schema.

## What's NOT here (sibling subsystems, documented separately)

- `d2_4_core_voice` (mention_translator, voice_decider, voice_profiles, voice_tracker) →
  state_core_voice.
- `d2_5_state_conversation` (dynamics_engine, message_context, affect_engine) →
  state_core_conversation. Note affect_engine reaches DOWN into `d1_1` sqlite_store (see CONNECTIONS B).