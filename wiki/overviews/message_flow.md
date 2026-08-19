---
type: overview
tags: [pipeline, messages, flow]
created: 2026-08-16
updated: 2026-08-16
sources: [docs/ARCHITECTURE.md, docs/SUBSYSTEM_pipeline_act.md, docs/SUBSYSTEM_pipeline_ingest.md]
status: seed
---

# Message Flow (text → reply)

## Intake funnel (`d3_2_discord_bot.py` → `on_message`)

Skips own-messages / non-text / DMs / empty-no-attachments; routes allowed vs passive channels;
short-circuits command handlers (!profile / !stats / !help); then calls
`message_manager.process_message`.

## Pipeline construction

`EnhancedMessageManagerV3.process_message` (see [[enhanced_message_manager_v3]]) builds a
`MessageContext` envelope (d1_3) and wires a fresh `MessagePipeline` via
`serin_di.build_message_pipeline(...)` — retrieval = `ConversationContextBuilder`,
plus the dynamics engine and affect engine (CONNECTIONS G at the source).

## The 10 stages (see [[message_pipeline]])

1. **ResponseDecisionStage** — reply / react / ignore via [[conversation_dynamics_engine]]
   (Boltzmann energy); creator mention → hard force-reply + `metadata.instant_reply`.
2. **MemoryRetrievalStage** — hybrid BM25+vector search via [[qdrant_memory_system]],
   `GARBAGE_PATTERNS` filter, summaries deprioritized, PyO3 `rerank_candidates` (fallback Python).
3. **ResponsePlannerStage** — belief-constrained plan ([[bayesian_beliefs]]).
4. **TemporalStage** — resolve date/time references.
5. **PersonalityStage** — inject persona + per-relationship tone.
6. **PromptAssemblyStage** — build full prompt (8 context sections); edge A: `store_prompt_debug`.
7. **LLMCallStage** — call the model; edge A: `update_last_prompt_debug` with latency.
8. **ResponseCleaningStage** — strip thinking tags (`filter_thinking`), contractions
   (`apply_contractions`), truncate.
9. **SendStage** — type + send; skips dynamics delay on instant replies.
10. **MemoryWriteStage** — **ALWAYS runs, even on halt**: perceives via `perceive_message`,
    stores via remember, `affect_engine.record_sentiment` (edge G feedback loop), writes memory.

## Halting semantics

The pipeline breaks early when the decision stage sets `halt_reason` — but the tail still runs
MemoryWriteStage, so perception/memory/personality/affect update for every message, even when
Serin stays silent. With `small_llm=None` the facts/beliefs stay empty (pinned by
`tests/test_fact_belief_gating.py`, the legacy-schema holdout — see [[known_debt]]).

## Observability (same run)

Stages broadcast to panel WebSocket clients (`runners_pipeline` events, `decision_temporal`
decision events); the prompt-debug buffer grows; `_ws_lock` guards the socket set.

## See also

[[architecture]] · [[message_pipeline]] · [[conversation_dynamics_engine]] · [[index]]
