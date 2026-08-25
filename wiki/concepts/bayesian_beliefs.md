---
type: concept
tags: [beliefs, memory, bayesian, schema]
created: 2026-08-16
updated: 2026-08-25
sources: [docs/SUBSYSTEM_pipeline_remember.md, docs/CONNECTIONS.md]
status: live
---

# Bayesian Beliefs & Evidence

## What it is

Serin's fact/belief knowledge system: claims accumulate evidence over time, and belief strength
is tracked with Bayesian machinery (belief, variance, log-odds) plus a corroboration /
contradiction ledger — replacing the legacy keyword-LIKE string state machine.

## Why it matters

This is the "imperfect, human memory" of [[causality_not_performance]] made concrete: Serin
doesn't dump facts; it holds *degrees of belief* that drift as evidence arrives — including
temporal decay, so stale impressions fade the way memory does.

## The state machine

`PENDING → SUPPORTED → CONTESTED → SUPERSEDED` (plus `UNKNOWN` in the legacy model).

## Where it lives

- **Authoritative DDL**: `d1_1_pipeline_flow/d2_4_flow_remember/d3_1_remember_core/d4_3_schema_store.py`
  — `facts` (Bayesian: `subject_id, claim, belief REAL DEFAULT 0.5, variance, log_odds,
  observation/corroboration/contradiction_count, primary_source, source_type, state,
  claim_hash UNIQUE`), `fact_observations` ledger, `beliefs` (supporting/contradicting
  fact ids, evidence_count...).
- **Active machinery**: d1_3 `d2_2_core_memory` — `BayesianBeliefEngine` wired in
  `d4_4_core_store.py:78-80` (`self.belief_engine = BayesianBeliefEngine(self.conn)`).
- **Consumers**: `ConversationContextBuilder` (facts 5 / beliefs 3 quotas), act
  `ResponsePlannerStage` (belief-constrained plans), `PromptAssemblyStage` (each belief must
  carry `content`; a `SUPPORTED` belief with `confidence >= 0.7` emits response constraints).

## Known issues (CONNECTIONS F)

- Three representations existed; exactly one is authoritative (above). The legacy d1_1 stores
  (`d5_1_belief_beliefs`, `d5_2_belief_evidence`) INSERT columns absent from the authoritative
  `facts` table (a real "no such column" risk) — their only consumer is
  `tests/test_fact_belief_gating.py` (tracked in git as of 2026-08-25; it was untracked at
  Phase-4 time; see [[known_debt]]).
- `perception_classify.py:245-248` lazily reaches in for the engine.

## See also

[[qdrant_memory_system]] · [[message_pipeline]] · [[known_debt]] · [[index]]
