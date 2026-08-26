---
type: overview
tags: [pipeline, messages, flow]
created: 2026-08-16
updated: 2026-08-25
sources: [docs/ARCHITECTURE.md, docs/SUBSYSTEM_pipeline_act.md, docs/SUBSYSTEM_pipeline_ingest.md]
status: live
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
8. **ResponseCleaningStage** — strip thinking tags (`filter_thinking`), then the single canonical
   `clean_response` (special tokens, name prefixes, mentions, whitespace, one 2000-char truncation).
   No contraction pass — the `apply_contractions` seam was deleted with the RNG humanizer
   (2026-08-18; see [[2026-08-18_vision_to_code_fix_plan]]).
9. **SendStage** — type + send; creator-override instant replies still respect the
   `min_send_delay = 0.4` latency floor (SERIN_VISION row 6).
10. **MemoryWriteStage** — **ALWAYS runs, even on halt**: perceives via `perceive_message`,
    stores via remember, `affect_engine.record_sentiment` (edge G feedback loop), writes memory.

## Halting semantics

The pipeline breaks early when the decision stage sets `halt_reason` — but the tail still runs
MemoryWriteStage, so perception/memory/personality/affect update for every message, even when
Serin stays silent. Fact/belief extraction runs through the **small LLM** (`SMALL_LLM_*` env keys,
aliased to the main LLM when unset — see [[qdrant_memory_system]]); with `small_llm=None` (backend
down) the facts/beliefs tables stay empty (negative path pinned by
`tests/test_fact_belief_gating.py`, positive accumulation path by
`tests/test_small_llm_accumulation.py`).

## Observability (same run)

Stages broadcast to panel WebSocket clients (`runners_pipeline` events, `decision_temporal`
decision events); the prompt-debug buffer grows; `_ws_lock` guards the socket set.

## See also

[[architecture]] · [[message_pipeline]] · [[conversation_dynamics_engine]] · [[index]]
