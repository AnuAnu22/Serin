---
type: entity
tags: [memory, qdrant, sqlite, bm25]
created: 2026-08-16
updated: 2026-08-16
sources: [docs/SUBSYSTEM_pipeline_remember.md, docs/CONNECTIONS.md, docs/SUBSYSTEM_state_core_db.md]
status: seed
---

# QdrantMemorySystem (the memory hub)

## What it is

The persistent-memory hub: Qdrant vector store + BM25 full-text + SQLite relational backing,
hybrid search with reranking. Everything the bot retains across conversations lives under this
subsystem: search, FTS, fact/belief tables, user profiles, relationships.

## Where it lives

- Hub: `serin/d1_1_pipeline_flow/d2_4_flow_remember/d3_1_remember_core/d4_4_core_store.py`
- Storage split-outs: `d4_1_core_storage/` (search / sqlite / write), `d4_2_connection_store`
  (Qdrant connection + Docker lifecycle), `d4_3_schema_store` (**authoritative SQLite schema**).
- The d1_3 `memory_store.py` twin is a **stale duplicate** (legacy schema, not in use).

## Key pieces

- **Authoritative schema** (`d4_3_schema_store.py`): `users`, `relationships`,
  `recent_messages`, `memory_fts` (FTS5), `facts` (Bayesian: belief/variance/log_odds/
  observation/corroboration/contradiction counts, `claim_hash UNIQUE`, state PENDING),
  `fact_observations` ledger, `beliefs` — see [[bayesian_beliefs]].
- **Hybrid retrieval**: BM25 (`d6_1_bm25_index.py`, PyO3 `sanitize_fts_query` seam) + vector
  search; rerank via PyO3 `rerank_candidates` (fallback `_rerank_results_simple`);
  recency decay ~30-day half-life.
- **Connection**: `connect_with_retry(host, port, max_attempts=3)` → Docker auto-start via
  docker-py (`ensure_qdrant_docker`); reads `config.QDRANT_*`.

## Consumers

Retrieval stage (via `ConversationContextBuilder.build_context` — type-specific quotas:
recent 15 / evidence 3 / episode 2 / utterance 2, mood-based filtering), MemoryWriteStage
(perceive + store), BackgroundProcessor (history reads), AffectEngine (lazy imports the
`d5_2_sqlite_store` for user_affect — edge B).

## Notes / Known issues

- The d1_3 `memory_store.py` CREATE TABLE conflicts with the authoritative schema (legacy
  `facts = id, content, category, confidence, source_message_id...`) — never the schema in use
  (CONNECTIONS F; see [[known_debt]]).
- `tests/memory/test_user_affect.py` pins the authoritative `user_affect` schema.

## See also

[[bayesian_beliefs]] · [[message_flow]] · [[known_debt]] · [[index]]
