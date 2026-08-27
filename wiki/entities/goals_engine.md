---
type: entity
tags: [entity, goals, growth, state]
created: 2026-08-26
updated: 2026-08-26
landed: C1 (schema+store) + C2 (formation/review machinery + maintenance wiring) + C3 (pursuit: decision energy + planner constraint) + C4 (persistence: boot-restore + shutdown flush)
sources: [docs/SERIN_VISION.md, serin/d1_1_pipeline_flow/d2_4_flow_remember/d3_1_remember_core/d4_3_schema_store.py]
status: live
---

# Goals Engine — self-generated persistent goals

## What it is

Serin's own cognitive-state machinery for goals she forms, revises, pursues, and drops.
Per SERIN_VISION "Growth": accumulated state that survives restarts, not a per-boot
simulation. The engine owns **machinery only** — formation, state machine, salience,
pursuit weighting, provenance. The **content** of a goal statement is whatever the
forming LLM produced and is stored verbatim; nothing curates, sanitizes, or templates it
(causality, not performance: pursuit weight comes from salience, never a die roll).

## Where it lives

- Schema: `goals` + `goal_evidence` tables in the authoritative `d4_3_schema_store.py`
  (status CHECK: FORMING / ACTIVE / PAUSED / ACHIEVED / DROPPED / SUPERSEDED; salience REAL;
  origin_provenance; parent_goal_id; last_reviewed_at).
- Row functions: `d4_1_core_storage/d5_6_goal_storage/d6_1_goals_store.py` (duck-typed store
  contract like [[conversation_dynamics_engine]]'s `d5_4_dynamics_store`; edge-B imports).
- Wiring (see [[message_flow]]): formation + review run inside BackgroundProcessor
  maintenance (`d5_1_tooling_background.py`, threshold-gated background-LLM seam — at most one new
  goal per cycle, gated by recent-message volume, live-goal cap, and LLM availability); the
  engine is attached on `EnhancedMessageManagerV3` and shared with the pipeline + processor
  (same duck-typed pattern as `dynamics_engine`/`affect_engine`). Pursuit (C3) adds
  salience-weighted energy in ResponseDecisionStage (via `_goal_salience_bonus`, 0.10 x
  salience per goal, bounded, no RNG) and goal-derived binding constraints via `ctx.response_plan`
  (top active goal quoted verbatim into constraints + `active_goals` key, slots ahead of belief
  constraints but respects the 3-slot cap) consumed by PromptAssemblyStage. Persistence (C4)
  mirrors ConversationDynamicsEngine: at boot core_manager calls
  goals_engine.restore_from_store() (loads live rows, verifies schema round-trips);
  at shutdown main_entry finally-block calls goals_engine.flush_to_store(force=True)
  which issues a final COMMIT so a hot reload (SIGTERM) cannot strand uncommitted
  goal rows. Mutations write through to the DB immediately, so the flush is a
  durability barrier, not a state transfer; panel exposure at GET /api/goals (C5).
- Tests: `tests/test_goals_store.py` (schema pin, transitions, terminal absorption,
  supersede provenance, salience clamps, pursuit order, review scheduling).

## State machine

`FORMING -> ACTIVE -> PAUSED -> ACTIVE* -> ACHIEVED | DROPPED | SUPERSEDED`. Terminal states
absorb (no transition leaves them); SUPERSEDED records its replacement as a `goal_evidence`
entry. Every goal carries an append-only evidence trail `(kind, detail, source, created_at)`
- formation context, review outcomes, supersession links all land there.

→ [[index]] · related: [[causality_not_performance]], [[bayesian_beliefs]], [[qdrant_memory_system]]
