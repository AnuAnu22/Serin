---
type: entity
tags: [ingest, pipeline, intake]
created: 2026-08-16
updated: 2026-08-16
sources: [docs/SUBSYSTEM_pipeline_ingest.md, docs/ARCHITECTURE.md]
status: seed
---

# EnhancedMessageManagerV3 (the ingest funnel)

## What it is

The front door + intake brain. Receives Discord messages from `on_message`, pre-processes them
(mentions, vision, corrections), builds a `MessageContext` envelope, wires a fresh
`MessagePipeline` via `serin_di.build_message_pipeline(...)`, and runs it. Outbound degree
~32 — the hub of the ingest subsystem.

## Where it lives

`serin/d1_1_pipeline_flow/d2_2_flow_ingest/d3_2_ingest_core/d4_4_core_manager.py`

## What it feeds

- **Context building** (`d3_1_ingest_context/`): `ConversationContextBuilder` (feeds the act
  MemoryRetrievalStage; type-specific retrieval quotas + narrative monologue formatting),
  `LongMessageHandler` (80w long / 150w wall / 8s complex reactions), canonical
  `MentionTranslator`.
- **Perception** (`d3_2_ingest_core/`): board/classify/personality/profile; visual-memory
  (CLIP) cortex; correction-learning handler; legacy `message_process` batch path.
- **Sync** (`d3_3_ingest_sync/`): `MessageCrawler` (quick-sync every 15 min + deep validation
  hourly) + `BackfillMixin`.

## Entanglement (ingest ↔ act)

`core_manager.process_message` builds the pipeline and passes in the d1_3
[[conversation_dynamics_engine]] + `UserAffectEngine` (CONNECTIONS G). Act's `MemoryWriteStage`
calls BACK into this subsystem (`perceive_message`, `extract_facts_from_message`,
`detect_contradictions`) — ingest and act are genuinely entangled.

## Notes / Known issues

- `tests/inspector/` and `test_pipeline_smoke.py` exercise its wiring.
- The canonical MentionTranslator lives HERE (pipeline copy); the d1_3 core_voice twin is dead
  (see [[known_debt]]).

## See also

[[message_pipeline]] · [[message_flow]] · [[serin_di]] · [[index]]
