# SUBSYSTEM: pipeline_remember — persistent memory + knowledge (d1_1 d2_4)

Checklist: 19/19 files read. Status: DRAFT (wip). Finalize name: `SUBSYSTEM_pipeline_remember.md`.

Root: `serin/d1_1_pipeline_flow/d2_4_flow_remember/`

## Scope & role in the system

The **persistent-memory + knowledge subsystem**. Everything the bot retains across
conversations lives here: vector search (Qdrant), full-text (BM25), relational state
(SQLite), fact/belief tables, and a handful of knowledge-assist helpers.

The subsystem has two physical halves plus three top-level helpers:

1. **`d3_1_remember_core/`** — the STORAGE ENGINE. `d4_4_core_store.py` is the single
   `QdrantMemorySystem` hub; the rest are split-out implementation modules
   (`d4_1_core_storage/` search/sqlite/write, `d4_2_connection_store`, `d4_3_schema_store`).
2. **`d3_2_remember_knowledge/`** — knowledge helpers. Mixed wiring: `d4_2_memory_context`
   is live; `d4_1_knowledge_belief/` (BeliefStore+FactStore), `d4_3_memory_quality`,
   `d4_4_knowledge_retrieval` are **dead near-duplicate code** (see findings).
3. **`d3_3_remember_qdrant.py`** (compat shim), **`d3_4_sync_monitor.py`** (live diagnostics),
   **`d3_5_remember_temporal.py`** (live natural-time parsing/formatting).

This is the authoritative home of the Qdrant/SQLite/BM25 memory, CONFIRMING CONNECTIONS F:
`d4_3_schema_store.py` here owns the Bayesian `facts`/`fact_observations`/`beliefs` schema
that the d1_3 `core_memory` stores depend on, and it is the correct `QdrantMemorySystem`
(the d1_3 `memory_store.py` one is a stale duplicate).

## Files

### d3_1_remember_core/d4_2_connection_store.py
Qdrant connection + Docker lifecycle. `connect_with_retry(host, port, max_attempts=3)` —
tries a direct client connect, on failure falls back to `ensure_qdrant_docker`
(Docker auto-start). `find_qdrant_container` / `ensure_qdrant_docker` use the
`docker` (docker-py) SDK to find or create/restart a Qdrant container and wait (30s).
Reads `config.QDRANT_USE_DOCKER` / `QDRANT_DOCKER_*`. Returns a live `qdrant_client`
client with `close()`.

### d3_1_remember_core/d4_3_schema_store.py
**AUTHORITATIVE SQLite schema.** `init_sqlite_schema(conn, cursor)` creates: `users`,
`relationships`, `activity_log`, `memory_fts` (FTS5, content=`memories`), `background_jobs`,
`qdrant_collections`, `memory_stats`, `recent_messages`, **`facts`** (Bayesian:
`id INTEGER PK, subject_id NOT NULL, subject_name, claim NOT NULL, category, belief REAL
DEFAULT 0.5, variance REAL DEFAULT 0.25, log_odds REAL DEFAULT 0.0, first_observed,
last_confirmed, last_challenged, observation_count, corroboration_count,
contradiction_count, primary_source, source_type, state DEFAULT 'PENDING', is_active,
claim_hash UNIQUE` + indexes on `(subject_id, is_active)` and `(state, is_active)`),
**`fact_observations`** ledger, **`beliefs`** (`id TEXT PK, content, category, state,
confidence, supporting_fact_ids, contradicting_fact_ids, evidence_count, claim_count,
timestamp, updated_at, last_contradicted_at, contradiction_resolved_at, is_active` +
indexes), and **`user_affect`** (per-user valence + familiarity, partial index). This is the
single source of truth for the fact/belief/affect tables that BOTH the d1_1 pipeline and the
d1_3 `core_memory` stores read/write (→ CONNECTIONS F).

### d3_1_remember_core/d4_1_core_storage/d5_1_search_store.py
Hybrid vector+keyword search. `search_hybrid` runs a Qdrant vector search (cosine) and an
BM25 full-text search, then merges via `_merge_candidates`: `combined_score = vector*0.6 +
(1/(1+bm25))*0.4`. `_build_qdrant_filter` builds vector filters from a class-attribute
`build_filter` (assigned by the core store). `_rerank_results_simple` is the **PyO3 seam at
line 168**: `import serin_core` → `rerank_candidates(scores, age_days_list)` with a Python
recency-boost fallback (→ CONNECTIONS D). `_condense_results` adds a `score_breakdown`
(per-facet point breakdown) for the control-panel memory browser. `_update_ingestion_stats`
tracks totals.

### d3_1_remember_core/d4_1_core_storage/d5_2_sqlite_store.py
SQLite CRUD layer: users (profile/relationships), recent messages, and the **`user_affect`
section (lines 176-240)** — `upsert_user_affect(store, user_id, valence, valence_updated,
familiarity_count, impression_text, impression_updated, since_impression)`,
`get_user_affect(store, user_id)`, `get_users_due_impression(store, limit=3)`. These are EXACTLY
the symbols the d1_3 `AffectEngine` lazily imports (→ CONNECTIONS B). Also `_sanitize_unicode`,
`store_recent_message` (20k/channel cap), `get_recent_conversation_from_sqlite`,
`cleanup_old_memories` (Qdrant scroll+delete + BM25 delete_documents). Wired by the core store
and read by d1_5 `tooling_background` (→ CONNECTIONS C).

### d3_1_remember_core/d4_1_core_storage/d5_3_write_store.py
Memory write path. `add_memory_enhanced`: `_generate_memory_id` (uuid5 from
source_message_id:chunk_index), `_chunk_content` (sentence-based 200-600 tokens),
`_build_payload` (rich payload incl. `person_id`, `timestamp_ts`, `importance`, `memory_type`,
`evidence_class`, `speech_act`, `is_objective`, `extracted_facts`, `topics`,
`summary_extract`/`abstract`, `embedding_model` `nomic-embed-text-v1.5`, `parent_id`,
`linked_ids`, `chunk_index/total_chunks`), `_is_duplicate`, `_queue_background_jobs`
(summarize + rerank jobs). **Calls `filter_for_memory(content)`** (imported from d1_3
`thinking_filter`) first, embeds via `store.embedding_model.encode`, upserts to Qdrant + BM25,
queues background jobs, `_update_ingestion_stats`, `log_memory` (debug_logger).

### d3_1_remember_core/d4_4_core_store.py
**THE authoritative `QdrantMemorySystem` hub (outbound ~30).** This is the class the pipeline
actually wires (serin_di → d3_3 → here). `__init__` (lines ~160-162) wires **ALL THREE belief
stores**: `self.fact_store = FactStore(self.conn)`, `self.belief_store =
BeliefStore(self.conn)` — both imported from **d1_3** (lines 78-79:
`d1_3_state_core/.../d3_1_belief_store`, `d3_2_evidence_store`) — plus
`self.belief_engine = BayesianBeliefEngine(self.conn)` (d1_3 `d3_3_belief_dynamics`).
Owns the Qdrant client (via `_connect_with_retry` → connection_store), the embedding model
(`all-MiniLM-L6-v2`, dim 384), the BM25 index (`SQLiteBM25Index`, memory_fts.db), and SQLite
(`bot_data.db`), init via `_init_sqlite_robust` (corruption handling) → `_init_sqlite_schema`
→ **d4_3_schema_store**. Sets up the Qdrant collection and exposes wrapper methods
(`search_hybrid`, `add_memory_enhanced`, `add_memory`, `search_memories`,
`get_relevant_facts`/`get_relevant_beliefs`, user/relationship/recent-message wrappers).
DISTINCT from the d1_3 `d3_4_memory_store.py` `QdrantMemorySystem` (stale duplicate w/ legacy
schema) — this is the real one.

### d3_1_remember_core/__init__.py, d4_1_core_storage/__init__.py — empty

### d3_2_remember_knowledge/d4_2_memory_context.py — **LIVE**
`EnhancedMemoryContext` (holder with `context_history`/`temporal_context`) and
`ImprovedSystemPrompt.get_enhanced_system_prompt()` (a fixed human-like system-prompt string).
Both imported by the ingest `d4_4_core_manager` (lines 37-38; used at 117 and 169). Lightweight;
the "enhanced" machinery is minimal here.

### d3_2_remember_knowledge/d4_1_knowledge_belief/d5_1_belief_beliefs.py — **DEAD in prod**
`BeliefStore` — a LEGACY-STYLE SQLite belief store (content/confidence state machine:
PENDING/SUPPORTED/CONTESTED/SUPERSEDED/UNKNOWN). `add_or_update_belief` writes `beliefs`
columns `id, content, category, state, confidence, supporting_fact_ids,
contradicting_fact_ids, evidence_count, claim_count, timestamp, updated_at,
last_contradicted_at, contradiction_resolved_at` — which ARE schema-compatible with the
authoritative `beliefs` DDL. `infer_beliefs_from_facts` (domain-specific "win condition" +
preference/identity knowledge rules) and `get_relevant_beliefs` (keyword LIKE).
**No production importer** — only `tests/test_fact_belief_gating.py` (untracked) uses it via
monkeypatch. The app wires the d1_3 `BeliefStore` instead.

### d3_2_remember_knowledge/d4_1_knowledge_belief/d5_2_belief_evidence.py — **DEAD AND SCHEMA-INCOMPATIBLE**
`FactStore` — a LEGACY-STYLE fact store. `add_fact` INSERTs `facts` columns
`id, content, category, confidence, source_message_id, source_user_id, source_username,
source_type, timestamp, updated_at` + auto-supersede (`board_state`/`game_result`/`reference`).
**These columns do NOT exist in the authoritative Bayesian `facts` table** (which has
`subject_id/claim/belief/variance/log_odds/claim_hash`, no `content/confidence/source_*`).
So against an authoritative-schema DB these INSERTs would fail. Only referenced by the
untracked test. This is a THIRD, stale facts representation in the repo (→ CONNECTIONS F refines).

### d3_2_remember_knowledge/d4_3_memory_quality.py — **DEAD**
`MemoryQualityAssessor` (clarity/density/emotional/personal/temporal scoring + thresholds +
suggestions). Zero references anywhere in serin/tests. Near-duplicate of scoring ideas already
in `d5_1_search_store`/`d4_4_knowledge_retrieval`.

### d3_2_remember_knowledge/d4_4_knowledge_retrieval.py — **DEAD**
`HumanLikeMemoryRetriever` + `PersonalityConsistencyAnalyzer` + `HumanLikeMemoryQuery`.
Sophisticated multi-pass "human-like" scoring (multi-strategy candidate gathering, weighted
relevance/recency/importance/personality/emotional scoring, conversation-aware filtering).
TYPE_CHECKING-only import of `QdrantMemorySystem`. **Zero references** — the real retrieval
path is `search_hybrid` on the core store.

### d3_2_remember_knowledge/__init__.py — empty; d4_1_knowledge_belief/__init__.py — `# intentionally empty`

### d3_3_remember_qdrant.py — **LIVE compat shim**
No implementation; re-exports `QdrantMemorySystem` from `d4_4_core_store` and
`SQLiteBM25Index` from **d1_3** `d6_1_bm25_index`. Docstring explains the split. Preserves
the historical import path (`serin.memory.qdrant`) so existing callers keep working. This is
why greps for `QdrantMemorySystem` surface both this shim and the two class definitions.

### d3_4_sync_monitor.py — **LIVE diagnostics**
`MemorySyncMonitor(memory_system, background_processor, message_crawler)`. An async loop
(`start_monitoring`, 30s cadence) that runs diagnostics: API-interface mismatch checks
(inspects `queue_message` signature), DB consistency (SQLite counts vs Qdrant), race-condition
signatures, memory pressure (queue utilization/drops, growth rate), sync-gap detection, and
performance analysis. `log_sync_failure`, `get_diagnostic_report`, `force_sync_check`.
Created via the serin_di `create_sync_monitor` factory and run by gateway
`pipeline_initializer:247-248` (`start_monitoring`).

### d3_5_remember_temporal.py — **LIVE natural-time**
Pure logic, no I/O. `TemporalParser` (parse "last Tuesday"/"this morning"/"2 weeks ago" →
datetime), `TemporalFormatter` (datetime → "This morning"/"Last Tuesday"/"2 weeks ago"),
`TemporalContext` (both + `extract_time_range`/`is_recent`), plus module convenience
`temporal`, `parse_time`, `format_time`, `get_time_range`. The ingest `context_builder`
(d1_1 d2_2) uses `TemporalFormatter.format_natural` (line 219) to render recency.

## Cross-cutting / notable findings (see CONNECTIONS.md)

1. **Authoritative storage lives here.** `d4_3_schema_store` owns the real Bayesian schema;
   `d4_4_core_store` is the real `QdrantMemorySystem` and wires the D1_3 belief/fact/engine
   classes. The d1_3 `core_memory` machinery depends on tables created here (CONNECTIONS F).
2. **Twelve of nineteen files are live; four knowledge files are DEAD near-duplicates:**
   `d5_1_belief_beliefs`, `d5_2_belief_evidence`, `d4_3_memory_quality`,
   `d4_4_knowledge_retrieval`. The two "human-like retriever/quality" modules are fully
   unreferenced; the app uses `search_hybrid`/`MemoryQualityAssessor`-style scoring spread
   elsewhere or the simpler keyword stores.
3. **Schema conflict sharpened (refines CONNECTIONS F):** the d1_1 `BeliefStore` (d5_1) is
   schema-compatible with the authoritative `beliefs`, but the d1_1 `FactStore` (d5_2) targets
   legacy `facts` columns that do not exist in the authoritative Bayesian `facts`. So within
   this subsystem there is a stale facts representation. The ONLY caller of these dead stores
   is the untracked `tests/test_fact_belief_gating.py`, which monkeypatches them onto the real
   connected `ms` — flag for Phase 4 (does that test even run against an authoritative DB?).
4. **Two `QdrantMemorySystem` classes exist in the repo**; this one (d4_4_core_store) is the
   live one; the d1_3 `memory_store.py` one is a stale duplicate (CONNECTIONS F).
5. **PyO3 seam** — `rerank_candidates` at `d5_1_search_store.py:168` (CONNECTIONS D).
6. **Cross-subsystem inbound/outbound:** `d5_2_sqlite_store` is imported by d1_3 affect_engine
   and d1_5 tooling_background (CONNECTIONS B/C); `d3_3` re-exports `SQLiteBM25Index` from d1_3.
7. The "human-like memory" ambitions (`knowledge_retrieval`, `memory_quality`) are scaffolding
   that did not get wired — reads as aspirational/experimental. Dedup candidates for Phase 4.

## What's NOT here
- The legacy `QdrantMemorySystem`/`SQLiteBM25Index` implementation that used to live in
  `d3_3_remember_qdrant.py` is gone — split into core_store + d1_3 bm25_index (the shim proves it).
- `SQLiteBM25Index` itself is defined in d1_3 (`d6_1_bm25_index`) — imported via the shim.
- Background processors that CONSUME memories (summarize/rerank jobs) are in ingest/ops subsystems.