---
type: entity
tags: [pipeline, act, stages]
created: 2026-08-16
updated: 2026-08-16
sources: [docs/SUBSYSTEM_pipeline_act.md, docs/ARCHITECTURE.md, docs/README.md]
status: seed
---

# MessagePipeline (the 10-stage DAG)

## What it is

The conductor of Serin's response engine. `MessagePipeline.build()` constructs exactly ten
stages in a fixed order; `process(ctx)` runs them, honoring halt semantics and the
always-run-MemoryWrite tail. Every stage extends `PipelineStage` (ABC) whose `run(ctx)`
wraps `_run(ctx)` with per-stage timing recorded into `ctx.stage_timings`.

## Where it lives

`serin/d1_1_pipeline_flow/d2_1_flow_act/d3_1_act_runners/d4_2_runners_pipeline.py`
(stages in `d3_2_act_stages/` + `d4_1_runners_dispatch/`; base in `d3_3_stages_base.py`).

## The 10 stages, in order

1. ResponseDecisionStage — reply/react/ignore (see [[conversation_dynamics_engine]])
2. MemoryRetrievalStage — hybrid BM25+vector via [[qdrant_memory_system]]
3. ResponsePlannerStage — belief-constrained plan ([[bayesian_beliefs]])
4. TemporalStage — resolve date references
5. PersonalityStage — persona + per-relationship tone
6. PromptAssemblyStage — build prompt (8 context sections)
7. LLMCallStage — call the model
8. ResponseCleaningStage — strip thinking tags, truncate
9. SendStage — type + send
10. MemoryWriteStage — ALWAYS runs, even on halt

## Key behavior

- **Halt semantics**: `process()` breaks on `ctx.halt_reason` (set by the decision stage or by
  a stage exception → `stage_error:<name>`), but the tail still runs `MemoryWriteStage` so
  perception/memory/affect update for every message.
- **Edge A (observability)**: stages broadcast to panel WebSocket clients and write the
  prompt-debug buffer (`store_prompt_debug` / `update_last_prompt_debug`) — d1_1 reaching
  down into d1_5 (see [[architecture]]).
- **Wiring**: built per-message by `EnhancedMessageManagerV3` via `serin_di.build_message_pipeline`
  with retrieval=ConversationContextBuilder, dynamics_engine, affect_engine (CONNECTIONS G).

## Notes / Known issues

- `test_pipeline.py` pins the exact 10-stage order byte-for-byte.
- The pipeline-inspector tool (`tools/pipeline_inspector/`) mirrors `process()` control flow
  by hand to inspect state at stage boundaries — see [[testing]].

## See also

[[message_flow]] · [[serin_di]] · [[enhanced_message_manager_v3]] · [[index]]
