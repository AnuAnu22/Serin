# SUBSYSTEM: pipeline_act — the message pipeline (d1_1 d2_1)

Checklist: 16/16 files read. Status: DRAFT (wip). Finalize name: `SUBSYSTEM_pipeline_act.md`.

Root: `serin/d1_1_pipeline_flow/d2_1_flow_act/`

## Scope & role in the system

**The decision-and-response engine of the bot.** This is where an inbound message becomes a
decision (reply/react/ignore) and, if answered, a fully processed natural-language reply. It is
the **act** counterpart to the ingest (`d2_2`, Subsystem 8) and remember (`d2_4`, Subsystem 5)
pipelines: ingest classifies and stores, remember persists, and this subsystem assembles a turn.

Two physical halves plus the shared base:

1. **`d3_1_act_runners/`** — the pipeline *runner + dispatch*. `d4_2_runners_pipeline.py` wires a
   10-stage DAG (`MessagePipeline`); `d4_1_runners_dispatch/` holds the LLM call, the send/dispatch
   stage, and the prompt-assembly stage.
2. **`d3_2_act_stages/`** — the *decision + context stages*: response decision, memory retrieval,
   memory write, and personality injection.
3. **`d3_3_stages_base.py`** — `PipelineStage(ABC)`, the base every stage extends.

The whole subsystem is **the primary place the lowest layer (d1_1) reaches up to the highest (d1_5
control panel)** — CONNECTIONS A is confirmed at three sites here (broadcast + two debug-buffer
writes). It is also a heavy consumer of the d1_3 `ConversationDynamicsEngine` (CONNECTIONS G),
And it is where belief logic (`ResponsePlannerStage`, imported from Subsystem 6) and perception
logic (`perceive_message`, imported from Subsystem 8) converge on a single run.

## Files

### d3_3_stages_base.py — PipelineStage(ABC)
`PipelineStage` is the base for ALL stages (inbound ~20). `name` property; `async def run(ctx)`
wraps the abstract `_run(ctx)` with per-stage timing recorded into `ctx.stage_timings` (a dict keyed
by stage name), with try/except logging+re-raise. Every concrete stage implements `_run(ctx) ->
MessageContext`. This timing wrapper is the same envelope (`MessageContext`, d1_3) every stage
mutates — the structural reason d1_3 is the low layer.

### d3_1_act_runners/d4_2_runners_pipeline.py — MessagePipeline (10-stage DAG)  ⭐
The conductor. `build()` constructs exactly these stages **in this order**:

1. `ResponseDecisionStage` — should we even respond? (decision_temporal); deterministically raises engagement salience from actively-pursued self-goals (see [[goals_engine]])
2. `MemoryRetrievalStage` — pull memories/profile/context (memory_retrieval)
3. `ResponsePlannerStage` — belief-constrained plan (via d2_5 response_planner); injects the top active self-goal as a binding constraint + ctx.response_plan["active_goals"] (see [[goals_engine]])
4. `TemporalStage` — resolve date references (decision_temporal)
5. `PersonalityStage` — inject persona + tone (personality_stage)
6. `PromptAssemblyStage` — build the actual prompt (prompt_assembly)
7. `LLMCallStage` — call the model (llm_call)
8. `ResponseCleaningStage` — strip thinking/tokens/truncate (response_cleaning)
9. `SendStage` — send the reply (dispatch_send)
10. `MemoryWriteStage` — persist the exchange (memory_write)

`process(ctx)` loops over the stages, broadcasting a `"pipeline_stage"` event per stage (the panel
observability pipe), **breaks out early when `ctx.halt_reason` is set** (decision stage can decide to
skip — reply/react/ignore), but **ALWAYS runs stage 10 `MemoryWriteStage` even on halt** so perception
and memory still happen for every message even when the bot doesn't answer. Timing for every stage is
left in `ctx.stage_timings`.

**CONNECTIONS A (confirmed, line 29-31):** imports `broadcast_event` from
`d1_5_ops_tooling/.../server_websocket` and calls it for stage events — the pipeline broadcasts live
execution to control-panel clients. Constructed by the ingest `core_manager` (Subsystem 8) which hands
it the d1_3 `ConversationDynamicsEngine` (CONNECTIONS G).

### d3_1_act_runners/d4_1_runners_dispatch/d5_1_llm_call.py — LLMCallStage
`LLMCallStage(response_generator)` wraps the Subsystem-6 `get_response_natural` chat path.
`_run` calls the generator with `current_messages=ctx.built_messages`, `context=ctx.context_block`,
`tone_modifier=ctx.tone_modifier` → `ctx.raw_response`. **CONNECTIONS A (line 34, confirmed):**
lazily imports `update_last_prompt_debug` (panel debug_routes) and records `(raw_response,
latency_ms)` into the panel's in-memory prompt-debug buffer after every call.

### d3_1_act_runners/d4_1_runners_dispatch/d5_1_prompt_assembly.py — PromptAssemblyStage
`PromptAssemblyStage(mention_translator, memory_system, affect_engine)`. `_run`:
- Sets `ctx.system_prompt` via `build_natural_system_prompt` (Subsystem 6) + `tone_modifier`; applies
  `_add_response_plan_constraints` from `ctx.response_plan` so the belief plan becomes binding prompt
  text.
- Builds 8 typed context sections via prompt_helpers: facts, beliefs, relationship, belief_evolution,
  missed_messages, memory, personality, user_profile → `ctx.context_block` + `ctx.built_messages`.
- Imports `get_missed_messages`/`clear_missed_messages` from `decision_temporal` (shared module state —
  see below).
- **CONNECTIONS A (line 260, confirmed):** lazily imports `store_prompt_debug` and pushes a full prompt
  snapshot dict (user, channel, system_prompt, memories, relationships, beliefs, user_message,
  full_prompt) into the panel debug store.

### d3_1_act_runners/d4_1_runners_dispatch/d5_2_prompt_helpers.py — context builders
Standalone prompt-construction helpers:
- `CONTEXT_BUDGET` — per-section token caps (facts/beliefs/relationship/belief_evolution/missed/
  memories/personality/user_profile/history).
- `_confidence_label` — BELIEF:SUPPORTED→"likely"/etc. label mapping.
- `_fuzz_memories` — deliberately *humanizes* the memory presentation: dedups by content hash and turns
  older/less-certain memories into vague phrasing ("I vaguely recall..."), so the prompt reads naturally
  rather than as raw data dumps.
- `_affect_context` — returns "" when familiarity < 0.1 (don't over-claim closeness).
- `_belief_evolution_context` — surfaces CONTESTED / SUPERSEDED / SUPPORTED belief drift via
  `memory_system.get_relevant_beliefs`.
- `_facts_context` — uses `memory_system.belief_engine.get_facts_for_user`.
- `_truncate_to_budget` — enforce per-section caps. This is the humanization/blending logic that turns
  retrieved store rows into "what the bot would say it knows."

### d3_1_act_runners/d4_1_runners_dispatch/d5_2_dispatch_send.py — SendStage (CONNECTIONS G)
`SendStage(dynamics)` carries the d1_3 `ConversationDynamicsEngine` (CONNECTIONS G, confirmed).
`_run` sends `ctx.final_response` via `ctx.channel.send`; simulates typing latency via
`dynamics.sample_delay(ctx.channel_id)` unless the decision stage flagged `instant_reply` (creator
override → 0.0 delay); fallback delay = `min(len*0.01, 3.0)+0.5`; sets
`ctx.metadata["message_sent"]`.

### d3_1_act_runners/d4_4_response_cleaning.py — ResponseCleaningStage
`ResponseCleaningStage(thinking_filter)` — the *output* hygiene stage. `_run(raw)`:
`filter_thinking` (d1_3 thinking_filter — itself a PyO3 seam) strips  thinking tags, then strips
special tokens, name prefixes, Discord `<@...>` mentions, excess whitespace, and truncates to 2000
chars → `ctx.final_response`.

### d3_2_act_stages/d4_1_decision_temporal.py — ResponseDecisionStage + TemporalStage (CONNECTIONS G)  ⭐
- **Shared module state (confirmed):** `_missed_messages: dict[str, list[dict]] = {}` module-level dict
  + `get_missed_messages(channel_id)` (2-hour cutoff) / `clear_missed_messages(channel_id)`. PromptAssembly
  imports these to show "messages you missed" — genuine cross-stage shared-memory via module globals.
- `ResponseDecisionStage(dynamics, creator_ids, affect_engine)` — the gate. Hard overrides: bot creator
  → `instant_reply` metadata; `@mention`; "serin" in content → always engage. Updates the d1_3 dynamics
  via `observe_message` + `allocate_attention`. Computes salience (0.3 base, +0.2 if '?', 1.0 if mentioned,
  +0.1×familiarity). Chooses reply/react/ignore via `dynamics.decide_action(...)`, sets `ctx.halt_reason`
  for skip, broadcasts a `"decision"` event (CONNECTIONS A), and the reactor path adds a reaction
  (`ctx.message.add_reaction`).
- `TemporalStage(temporal_context)` calls `self.temporal.resolve_dates(ctx.raw_content)`. NOTE: the d2_5
  `TemporalContext` provides `parse/format/extract_time_range/is_recent` but NOT `resolve_dates` — the
  call is presumably guarded by duck-typing; verify wiring in Phase 4.

### d3_2_act_stages/d4_2_memory_retrieval.py — MemoryRetrievalStage
`MemoryRetrievalStage(memory_system, retrieval)`. `_run`:
- `ctx.user_profile` via `memory_system.get_user_profile`.
- Builds context via `retrieval.build_context(user_messages, channel_id, mood_state)` (the ingest
  context_builder), then extracts `facts/beliefs/evidence_memories/episode_memories/utterance_memories`.
- **`GARBAGE_PATTERNS` filter** — drops rows whose content matches prompt-fragment phrases
  ("Summary:", "CRITICAL RULES", "### FINAL", "template", ...) that are LLM-artifacts, not real memory.
- **Summary deprioritization** — if evidence memories share ≥2 content words with episode memories, the
  summary episode is dropped (raw evidence preferred over redundant summaries).
- Flattens `ctx.memories = evidence + episode + utterance`; sets `recent_messages`, `relationships`.

### d3_2_act_stages/d4_3_memory_write.py — MemoryWriteStage  ⭐ (runs even on halt)
`MemoryWriteStage(memory_system, personality, client, small_llm, affect_engine)`. Replaces the old
`d4_5_message_process` code path for the post-send side. **Runs for EVERY message, even when the pipeline
halted (bot didn't reply).** For each content message:
1. **Sentiment (nltk `SentimentIntensityAnalyzer`)** → `emotional_tone` bucket.
2. **Per-user affect** — `affect_engine.record_sentiment(user_id, compound)` (CONNECTIONS G).
3. **Perception** — imports `perceive_message` (from **Subsystem 8**, d2_2 ingest) and runs it,
   producing `extracted_facts`/`speech_act`/`evidence_class`.
4. **Store user message** — `memory.add_memory_enhanced(...)` with perception metadata.
5. **LLM fact extraction (Bayesian)** — via `extract_facts_from_message` + `detect_contradictions`
   (Subsystem 8 perception_classify) → `memory.belief_engine.store_fact(...)` / `.observe(...,"contradict")`.
6. **Personality** — `personality.update_from_conversation(..., user_id, relationship)`; the
   relationship bucket comes from `relationship_category(affect snapshot)` so per-user mood is
   biased by standing (friend/stranger/enemy) at write time.
7. **Relationship** — `memory.update_relationship(bot_user_id, user_id)`.
8. **Activity** — `memory.log_activity(...)`.
Then, if `ctx.final_response` exists, stores the bot's reply as a `bot_response` memory.
→ This stage is the **write-back bridge into Subsystem 5 (remember)** and threads perception through the
act path.

### d3_2_act_stages/d4_4_personality_stage.py — PersonalityStage
`PersonalityStage(personality, mood_state)`. `_run`: `tone_modifier` from `mood_state.get_tone_modifier(ctx.user_id)` (scoped to the message author so a friend reads warmer than an enemy — per-relationship mood, CODING_GUIDELINES §4)
(`PersonalityState`, Subsystem 6) falling back to `personality.get_tone_modifier()`; `ctx.personality_context`
via `personality.get_personality_context()` (BotPersonality, Subsystem 6).

### Empty `__init__.py` — d2_1_flow_act, d3_1_act_runners, d4_1_runners_dispatch, d4_3_prompt_assembly,
d3_2_act_stages (all empty or `# intentionally empty`).

## The 10-stage order (read-in-sequence; is the contract)

```
Decision → Retrieval → Plan(belief) → Temporal → Personality → Assemble(prompt) → LLM → Clean → Send → Write
```
Early-exit: stages 1 sets `halt_reason`; `process()` breaks, but stage 10 `MemoryWriteStage` STILL runs.

## Cross-cutting / notable findings (see CONNECTIONS.md)

1. **CONNECTIONS A confirmed at 3 sites:** `broadcast_event` (runners_pipeline, per-stage "pipeline_stage"
   events), `update_last_prompt_debug` (llm_call), `store_prompt_debug` (prompt_assembly). The pipeline
   layer streams live events + full prompt snapshots into the d1_5 control panel — a genuine
   lowest-reaches-highest observability seam and cross-subsystem shared-memory channel.
2. **CONNECTIONS G confirmed (2 sites):** `SendStage` and `ResponseDecisionStage` both carry the d1_3
   `ConversationDynamicsEngine`; `MemoryWriteStage` feeds it back (`record_sentiment`). The decision to
   speak and HOW to time/speak it are driven by continuous physics state.
3. **Shared module state `_missed_messages`** in decision_temporal is consumed by prompt_assembly
   (`get/clear_missed_messages`) — cross-stage coupling via module globals, not the ctx envelope.
4. **Belief logic bridge:** `ResponsePlannerStage` (Subsystem 6) produces `ctx.response_plan`, and
   `PromptAssemblyStage._add_response_plan_constraints` turns it into binding prompt text — the concrete
   path by which Bayesian beliefs constrain output.
5. **Act reaches back into ingest:** `MemoryWriteStage` imports `perceive_message` +
   `extract_facts_from_message` + `detect_contradictions` from **d2_2** (Subsystem 8) — the write-back path
   is not a loop, it's a forward call into the perception/core of the same d1_1 layer.
6. **MemoryWriteStage is the always-on tail** — intentionally runs even on halt so perception/personality/
   affect update for every message regardless of whether the bot responds.
7. **Docs interplay:** `Context budget`+`_fuzz_memories` in prompt_helpers is where raw store rows get
   humanized into persona voice before the LLM sees them.
8. **TemporalStage duck-typing caveat:** `resolve_dates` is called but the d2_5 `TemporalContext` object
   doesn't define it — flag for Phase 4 verification.

## What's NOT here
- The ingest/classification side (`d2_2`, Subsystem 8) — `core_manager` constructs + feeds this pipeline;
  `perceive_message` is imported from here.
- The personality/response-generation brains (`d2_5`, Subsystem 6) — `get_response_natural`,
  `ResponsePlannerStage`, `PersonalityState`, `BotPersonality` are consumed here.
- The persistent memory (`d2_4`, Subsystem 5) — `QdrantMemorySystem`/`belief_engine` are written by
  `MemoryWriteStage` and read by `MemoryRetrievalStage`.
- The panel server + debug routes (d1_5, Subsystem 12) — only the `broadcast_event`/`update_last_prompt_debug`/
  `store_prompt_debug` target symbols live here.