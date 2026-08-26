# SUBSYSTEM: state_core_context — d1_3_state_core (core_voice + state_conversation)

Checklist: 9/9 files read. Status: DRAFT (wip). Finalize name: `SUBSYSTEM_state_core_context.md`.

Paths under `serin/d1_3_state_core/`.

## Scope & role in the system

This subsystem is CONVERSATIONAL STATE + VOICE DECISION state, implemented as pure capability
code (no pipeline stage of its own). It supplies:

- **Conversation state** (`d2_5_state_conversation`) — the physics-based decision engine that
  decides whether/how the bot responds, the shared `MessageContext` envelope, and the per-user
  sentiment/affect tracker.
- **Voice decision state** (`d2_4_core_voice`) — mention translation (for bot-facing text),
  structured voice join/leave decisions, TTS voice profiles, and voice-activity tracking.

This is the same `d1_3_state_core` directory as `state_core_db`; those two docs split it as
data/model (db_protect+core_memory+model_system) vs context/voice (this subsystem).

## Files

### d2_5_state_conversation (conversation state)

- `d3_1_dynamics_engine.py` — **ConversationDynamicsEngine**. A continuous physics simulation
  that REPLACES the 12 Boolean rules in `ResponseController.should_respond()` (rules 4-12) with
  mathematical models: Markowitz Portfolio Theory (global channel attention allocation),
  Kuramoto Oscillator (per-channel momentum/phase/frequency), KL Divergence (topic-shift
  detection → shatters momentum), Boltzmann Distribution (action selection: reply/react/ignore),
  Hawkes Process (response/reaction timing). `observe_message()` is called for EVERY message the
  bot sees. `decide_action()` supports per-user valence+familiarity bias toward "reply". Rules
  1-3 from ResponseController (creator, @mention, bot-name) are HARD OVERRIDES checked BEFORE the
  engine. Exposes `get_state_for_panel()` for the ops control panel.
  **PERSISTENT (2026-08-26):** per-channel state survives restarts via the `channel_dynamics`
  SQLite table (`d4_3_schema_store.py` DDL; `d4_1_core_storage/d5_4_dynamics_store.py` row
  functions). Boot-restore in ingest core_manager; force-flush in run_maintenance + main()
  shutdown; engine-side throttle 60s. Pinned by `tests/test_dynamics_persistence.py`.
  **NOTE divergence:** uses `logging.getLogger("serin")` (stdlib) directly — note this is the
  same logger object `d2_3_core_logger.setup()` configures; the divergence is configuration
  order only, not a separate pipeline.
- `d3_2_message_context.py` — **MessageContext** (dataclass). THE cross-cutting data envelope
  flowing through the entire message pipeline. Every stage reads from and writes to one; the
  module docstring states "No stage has side effects outside of what it writes into the context."
  Sections: input (message, ids, raw_content), decision (should_respond, halt_reason,
  is_mentioned, intent, response_plan), memory retrieval (memories/facts/beliefs/evidence/episode
  /utterance/recent_messages/user_profile/relationships — facts "From FactStore", beliefs "From
  BeliefStore"), temporal/context (personality_context, tone_modifier), prompt assembly
  (system_prompt, context_block, built_messages), LLM response (raw_response, final_response),
  and observability (stage_timings, metadata). Inbound ~23 — this is the contract joining all d1_1
  pipeline subsystems.
- `d3_3_affect_engine.py` — **UserAffectEngine** + AffectSnapshot. Per-user sentiment valence
  [-1,1], familiarity [0,1) (from message count, log scale), and qualitative LLM "impressions"
  injected into the prompt. Valence nudged ±0.05 per message (`SENTIMENT_GAIN`) and decays toward
  neutral with a 72-hour half-life; LLM impressions adjust valence (capped ±0.20) and store text
  (≤200 chars). Write-through cache (`_cache`, `_rows`); on cache miss schedules a background
  DB load. **Store is duck-typed/DI'd "never imported here (depth DAG compliance)"** — a
  consequence of top-level import discipline — but the module lazily function-imports
  `get_user_affect` / `upsert_user_affect` from `d1_1_pipeline_flow/.../d5_2_sqlite_store.py`
  (the CONNECTIONS-B seam). `build_impression_prompt()` / `parse_impression()` handle the LLM.
- `__init__.py` — empty.
- `d3_4_goals_engine.py` — **GoalsEngine** (self-generated persistent goals). Owns the
  goal lifecycle MACHINERY only: formation parsing, review decay, promotion, pursuit reads.
  Content of a goal statement is never curated or sanitized — it is whatever the forming LLM
  returned, validated only as JSON and stored verbatim (causality, not performance). Storage is
  duck-typed/DI'd like the affect engine: it function-imports
  `d5_6_goal_storage.d6_1_goals_store` (the CONNECTIONS-B seam). `build_formation_prompt()` /
  `parse_formation()` handle the LLM; `review_due()` decays salience deterministically and
  auto-drops goals below the floor; `pursuit_snapshot()` is the salience-ordered read consumed by
  the pipeline. Formation + review are driven from BackgroundProcessor maintenance
  (threshold-gated); see [[goals_engine]].

### d2_4_core_voice (voice decision state)

- `d3_1_mention_translator.py` — **MentionTranslator**. Bidirectional Discord mention ↔
  readable name conversion (`<@id>` → `@Name` for bot/memory, `@Name` → `<@id>` for sending).
  Built on a `discord.Client` with user/name caches, guild-member cache preload, and
  `clean_bot_self_mention()`.
  ⚠️ **DUPLICATE / LIKELY DEAD:** a near-identical `MentionTranslator` exists at
  `d1_1_pipeline_flow/.../ingest_context/d4_3_mention_translator.py`, and EVERY importer in the
  repo (serin_di, core_manager, sync_crawler/backfill, message_process, discord_bot,
  pipeline_initializer, passive_monitor) imports the PIPELINE one. Nothing imports this
  `core_voice` copy. Flag for dedup (see CONNECTIONS G).
- `d3_2_voice_decider.py` — **VoiceActionDecider**. Structured-output voice decision
  (join/leave/none + reason) via a lightweight LLM call (`ModelInterface.chat_completion` with
  JSON response_format). Keyword heuristic `_has_voice_intent()` fast-path skips the LLM call when
  no voice intent; `_parse_decision()` has a lenient Json repair path. Part of the "thinking/
  response pipeline (Option C)".
- `d3_3_voice_profiles.py` — **VoiceProfile** + **VoiceProfileManager**. Per-context TTS voice
  characteristics (speed, temperature, length_penalty, repetition_penalty). Ships 8 default
  profiles (default/casual/energetic/calm/sarcastic/serious/excited/tired), mood→profile mapping,
  custom profiles, and a module-global `get_profile_manager()` singleton. Use of the compatibility
  params signals a Kobold/llm-based TTS backend. Consumed by ops `voice_manager` / gateway TTS.
- `d3_4_voice_tracker.py` — **VoiceTracker**. Tracks who joins/leaves/switches voice channels and
  session durations; writes each transition to memory (`memory_system.add_memory` with
  duration-based importance). Uses `log_voice` from the debug logger (file-relative log dir). Also
  provides randomized natural voice-join / long-session reactions (`get_voice_join_reaction`,
  `get_voice_duration_reaction`) for message_manager integration.
- `__init__.py` — empty.

## Cross-cutting / notable findings (see CONNECTIONS.md)

1. **`MessageContext` is the pipeline-wide contract.** Defined here in d1_3 but read/written by
   every d1_1 stage. It literally carries facts/beliefs loaded from the FactStore/BeliefStore (also
   in d1_3) and the user_profile/relationships loaded from memory. This dataclass is the structural
   reason d1_3 is "low layer" — everything depends on this envelope.
2. **`ConversationDynamicsEngine` spans THREE subsystems (d1_3 → d1_1 → d1_5).** Instantiated by
   ingest `core_manager` (d1_1), passed into the message pipeline constructor
   (`runners_pipeline.py:89`), consulted by `decision_temporal` (act) and `dispatch_send` (Hawkes
   timing), AND read by the ops control panel via `engine.get_state_for_panel()` in
   `debug_routes.py:306-309` + `personality_routes.py:141` (d1_5). A genuine shared-state object
   whose state is produced in ingest/act and observed in the ops layer.
3. **`UserAffectEngine` store seam (CONNECTIONS B) is CONFIRMED with exact symbols:**
   lazy function imports of `get_user_affect` / `upsert_user_affect` from
   `d1_1_pipeline_flow/.../d5_2_sqlite_store.py`. The docstring claims the store is "never imported
   here" for DAG compliance — realized as function-scoped imports (still avoids a top-level cycle).
4. **Duplicate `MentionTranslator` (CONNECTIONS G).** Two implementations exist; the `core_voice`
   one is UNREFERENCED (all 10 import sites use the pipeline `d4_3_mention_translator.py`). Appears
   to be dead/duplicate code worth removing or consolidating.
5. `ConversationDynamicsEngine` uses stdlib `logging.getLogger("serin")` rather than the custom
   `core_logger` — an inconsistency with the rest of the codebase (minor, but notable for the log
   file-relative path story).

## What's NOT here

- `d1_3` data/model (db_protect, core_memory belief/fact/memory, model_system) →
  state_core_db (documented separately).
- The voice *gateway* implementation (audio, Rust bridge, TTS engine) lives in `d1_2_gateway_io`
  → subsystems 10-11, and `d2_4_core_voice` here provides only decision-state building blocks.
  `d2_5_state_conversation`'s consumers are all in `d1_1`. The pipeline `d4_3_mention_translator.py`
  (the wired one) is documented in Subsystem 8 (pipeline_ingest).