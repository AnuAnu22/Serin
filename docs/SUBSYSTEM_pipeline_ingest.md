# SUBSYSTEM: pipeline_ingest — message intake, perception, sync (d1_1 d2_2)

Checklist: 21/21 files read. Status: DRAFT (wip). Finalize name: `SUBSYSTEM_pipeline_ingest.md`.

Root: `serin/d1_1_pipeline_flow/d2_2_flow_ingest/`

## Scope & role in the system

The **front door + intake brain** of the bot. Everything that happens when a Discord message arrives
before the response pipeline runs, plus the background crawler that keeps memory in sync:

1. **`d3_1_ingest_context/`** — context building for the act pipeline: `ConversationContextBuilder`
   (feeds the act `MemoryRetrievalStage`), `LongMessageHandler`, the canonical `MentionTranslator`.
2. **`d3_2_ingest_core/`** — the intake core: the **`EnhancedMessageManagerV3` hub** (outbound 32)
   that receives messages, pre-processes them (mentions, vision, corrections) and hands them to the
   Subsystem-7 `MessagePipeline`; the perception layer (board/classify/personality/profile); the
   visual-memory (CLIP) cortex; the correction-learning handler; and the **legacy `message_process`
   batch path**.
3. **`d3_3_ingest_sync/`** — `MessageCrawler` (quick-sync every 15 min + deep validation every hour)
   + `BackfillMixin` for retroactive memory fills.

**The critical structural fact:** Subsystem 8 is what *feeds* Subsystem 7. `core_manager.process_message`
builds a `MessageContext` (d1_3) and runs `MessagePipeline` on it — wiring every stage of the act DAG and
passing in the d1_3 `ConversationDynamicsEngine` + `UserAffectEngine` (CONNECTIONS G). And Subsystem 7's
`MemoryWriteStage` calls **back into this subsystem** (`perceive_message`,
`extract_facts_from_message`, `detect_contradictions`) — so ingest and act are genuinely entangled.

## Files

### d3_1_ingest_context/d4_1_context_builder.py — ConversationContextBuilder (the act retrieval)
`ConversationContextBuilder(memory_system)` — the object passed to `MessagePipeline.build(retrieval=...)`
(Used only by Subsystem-7 `MemoryRetrievalStage` via `build_context`). Methods:
- `build_context(user_messages, channel_id, mood_state)` — type-specific retrieval so one memory type
  can't dominate: recent SQLite conversation (15), then SEPARATE `search_memories` calls for evidence(3)/
  episode(2)/utterance(2), mood-based filtering (chill tone strips argument memories; energetic raises
  utterance limit), relationships (min strength 0.3), per-user profiles, facts (5), beliefs (3).
- `format_context_for_llm(context)` — renders context as a **narrative internal monologue**
  ("--- CURRENT SITUATION ---", "--- INTERNAL MEMORY STREAM ---") with `TemporalFormatter.format_natural`
  timestamps; forces the LLM to synthesize rather than read a list. Used by the voice path.
- `resolve_referents` — naive "them/that/it" → capitalized-entity resolution, appended as a `[Note]`.
- `extract_time_reference_from_query` / `_search_with_time_range` — NLP time-time helpers.
Cross-subsystem: imports `TemporalFormatter` from d1_1 d2_4 (Subsystem 5).

### d3_1_ingest_context/d4_2_long_message.py — LongMessageHandler (human length reactions)
`LongMessageHandler` — reacts naturally to walls of text (80 w = long, 150 w = wall, 8 s = complex).
`should_react_to_length` (15% base chance, +15% for walls, halved when engaged),
`get_length_reaction` (curated "damn that's an essay lol" templates via `secrets`),
`get_context_note` for the LLM. `get_length_handler()` module singleton. Whether any caller wires this is
Phase-4 to confirm — `analyze_message_length` convenience is available but its integration point wasn't
seen in the manager/pipeline reads.

### d3_1_ingest_context/d4_3_mention_translator.py — MentionTranslator (the canonical copy)  ⭐
**The wired `MentionTranslator`** (CONNECTIONS H — the d1_3 `core_voice` copy is the dead duplicate). This
is the copy imported by core_manager, sync_crawler, backfill, passive_monitor (d1_5), serin_di.
Bidirectional Discord-mention conversion: `clean_for_bot` (`<@123>` → `@Name` for memory/LLM) and
`restore_for_discord` (`@Name` → `<@123>` for sending), `clean_bot_self_mention` (drop `<@bot>`), plus a
bidirectional user cache (`update_cache`, `cache_guild_members` at on_ready). Requires the `discord.Client`.

### d3_2_ingest_core/__init__.py, d4_1_core_perception/__init__.py
- ingest_core `__init__` empty. perception `__init__` is the **folder-form re-export** of the former
  `perception.py` (Rule 2: >500-line file → folder). Re-exports `parse_board/derive_from_board`,
  `perceive_message`/`detect_evidence`/`EVIDENCE_PATTERNS`, `analyze_personality`/`get_emotional_tone`/
  `detect_topic`, `get_user_profile`/`get_memory_stats`/`MessageManagerV3`, and `PerceptionResult` +
  pattern lists, plus backward-compatible `_`-prefixed private aliases.

### d4_1_core_perception/d5_1_perception_board.py — game-board fact extraction
`parse_board` — pipe-delimited `|X|O| |` strings → 2D grid (Connect-4 6×7, tic-tac-toe 3×3; None if
unparseable). `derive_from_board` — detects win conditions (4-in-a-row / 3-in-a-row, all 4 directions)
→ derived `game_result` facts; non-game boards → a generic `board_state` fact. Pure logic, no I/O.

### d4_1_core_perception/d5_2_perception_classify.py — perceive_message + evidence + LLM extraction  ⭐
The classification engine. `perceive_message(self, content, user_id, username) -> PerceptionResult`:
speech-act analysis (question/joke/sarcasm/agreement/disagreement/evidence/instruction/statement),
evidence extraction (boards/URLs/code/quotes → `evidence_blocks`), claim detection via
`CLAIM_PATTERNS` (win_claim/loss_attribution/self_assessment/other_correction/emphasis_claim + first-person
and second-person regex), observation/fact extraction, game-board fact derivation, evidence-class
(world/conversation/social), intent classification (question/seek_explanation/seek_validation/seek_joke/
seek_argument/command/social).
Two async LLM helpers (small/fast model, JSON-array prompts):
- `extract_facts_from_message` → list of `{subject_username, claim, category, confidence, source_type}`
  (used by Subsystem-7 `MemoryWriteStage` to feed the Bayesian engine).
- `detect_contradictions` → **reaches into d1_3**: lazily imports `BayesianBeliefEngine` from
  `d1_3 d2_2 d3_3_belief_dynamics`, fetches `get_facts_for_user`, asks the LLM which fact numbers the new
  message contradicts → returns fact_ids (used by `MemoryWriteStage` → `belief_engine.observe(...,"contradict")`).
  This is the d1_1→d1_3 lazy reach-in complementing CONNECTIONS F.

### d4_1_core_perception/d5_3_perception_personality.py — trait + tone + topic
`analyze_personality` — heuristic traits (humorous/polite/verbose/concise/enthusiastic) + interest
keywords (gaming/anime/music/tech/art); persists via `self.memory.update_user_traits`.
`get_emotional_tone(sentiment_score)`, `detect_topic` (keywords over 8 topic buckets).

### d4_1_core_perception/d5_4_perception_profile.py — profile accessors + alias
`get_user_profile`/`get_memory_stats` (thin wrappers over `self.memory`), and
`MessageManagerV3 = EnhancedMessageManagerV3` — a backward-compat alias importing the manager from
d4_4_core_manager (back-eddy: perception→core_manager; harmless since it's just a class ref at import).

### d4_1_core_perception/d5_5_perception_helpers/ — PerceptionResult + patterns
`d6_1_perception_result.py` defines the pattern constants (`CLAIM_PATTERNS`, `SARCASM_MARKERS`,
`JOKE_MARKERS`, `ARGUMENT_KEYWORDS`) and the **`PerceptionResult` dataclass** — the structured contract
carried into memory storage: `speech_act`, `is_objective`, `evidence_class`,
`intent`, `evidence_blocks`, `claims`, `observations`, `extracted_facts`. `__init__` is empty.

### d4_2_core_vision/d5_1_visual_memory.py — VisualMemorySystem (CLIP visual cortex)
`VisualMemorySystem(qdrant_client, collection="visual_memory")` — a **separate Qdrant collection** (dim 512,
cosine) for CLIP image embeddings (`clip-ViT-B-32` via SentenceTransformer; graceful if model fails).
`store_image_memory`/`store_image_from_bytes`, `recall_image`/`recall_image_from_bytes` (query_points,
threshold 0.85). `analyze_image` is **deprecated** — raises NotImplementedError ("image analysis is now
handled by the VLM directly"). Instantiated by core_manager when Qdrant is present.

### d4_3_correction_handler.py — learning from corrections
`CorrectionDetector.detect_correction(message, previous_bot_response, context)` — regex patterns
("no that's wrong", "actually it's", "you're wrong", "change X to Y", "I meant X"); returns a correction
dict with `original_statement`/`corrected_statement`/`correction_type`/`confidence`. `MemoryCorrector`
applies it: searches related memories, stores the correction as a high-importance (0.95) memory
(`"{corrected} (corrected from: {original})"`). `get_correction_acknowledgment` — natural "oh my bad, got it"
templates. Used by core_manager + the legacy message_process.

### d4_4_core_manager.py — EnhancedMessageManagerV3 (the intake hub, outbound 32)  ⭐
**The main message manager.** Docstring: "exists for backwards compatibility. New code should use
`MessagePipeline` directly" — but in practice it owns the intake flow and **builds + drives** the pipeline.
`__init__`: holds client, mention_translator, memory system (QdrantMemorySystem), main LLM connector
(get_model_connector via d1_3 factory) + optional vision LLM (SmolVLM); inits `PersonalityState`,
`ConversationAnalyzer`, `BotPersonality`, `CorrectionDetector`+`MemoryCorrector`, `VoiceTracker`,
`ConversationDynamicsEngine` **(CONNECTIONS G)** + `UserAffectEngine`, `VisualMemorySystem`
(if Qdrant), `VoiceActionDecider`, and an `EnhancedMemoryContext`/`ConversationContextBuilder`. Tracks a
`current_state` brain-state dict and `stats`.
`process_message(message)` (the pipeline-fed path): on first call builds
`MessagePipeline.build(memory_system, retrieval=self.context_builder, personality=bot_personality,
temporal_context=enhanced_context, response_generator=get_response_natural, thinking_filter,
mention_translator, mood_state=personality, client, small_llm, dynamics_engine, affect_engine)`
→ the **wiring point for Subsystem 7's 10-stage DAG**; handles image attachments (background
vision description via rate-limited semaphore), stores the recent message, builds a `MessageContext`
(d1_3) with `pending_visual_contexts`+`abort_flag` metadata, runs `pipeline.process(ctx)`, records
`final_response`, then `_check_voice_action` (VoiceActionDecider → join/leave via callback).
`_flush_batch_with_enhanced_context` is the older batch path (same pipeline build; metadata carries
`batch_size`/`bot_mentioned`).

### d4_5_message_process.py — legacy batch path (largely superseded)  ⭐
Module-level `self`-bound functions that were historically attached to the message manager:
`process_message` (mention-clean → correction check → vision fallback → `_update_user_profile` →
sentiment (vader) → `_process_perception_and_store` → `_analyze_personality` → batch flush;
immediate if bot mentioned), `process_voice_input` (Whisper-STT path: build context via
`context_builder.format_context_for_llm`, call `get_response_natural`, speak via voice_output_manager),
`_handle_correction`, `_handle_vision_fallback`/`_archive_image` (recall + store via VisualMemorySystem),
`_process_perception_and_store` (add_memory_enhanced + `belief_engine.store_fact`).
NOTE: the manager's **live `process_message` is in d4_4_core_manager, NOT this module's** — these
`self`-bound functions appear to be the legacy/batched intake that `core_manager.process_message` +
`_flush_batch_with_enhanced_context` superseded. Also references `self._perceive_message`, `_get_emotional_tone`,
`_analyze_personality`, `_schedule_flush_batch` which aren't defined in this file (mixed-in). This module
is a Phase-4 dedup/legacy candidate.

### d3_3_ingest_sync/__init__.py (empty), d4_1_sync_backfill.py — BackfillMixin
`BackfillMixin` provides crawler backfill methods (consumed by MessageCrawler):
`_backfill_channel` (full history, 100-msg batches → `bg_processor.queue_message`, 2s rate-limit sleep),
`_backfill_from_timestamp` (5-msg context batches), `_backfill_around_position` (±50 around a gap),
`_process_batch_with_context` (pulls ±2 surrounding SQL context, dedups, sorts, queues). Cleans mentions
via the canonical MentionTranslator.

### d3_3_ingest_sync/d4_2_sync_crawler.py — MessageCrawler (retroactive memory sync)
`MessageCrawler(client, memory_system, background_processor, mention_translator)` + `BackfillMixin`.
Two async loops: **quick sync** (every 15 min — compares latest Discord msg id to latest SQL; backfills on
mismatch, first sync backfills up to 20000), **deep validation** (every hour, after 10-min initial delay —
checks every 100th SQL message against Discord; gaps → `_backfill_around_position`; sequential channels with
10s delays + 10s between 10-checkpoint batches to respect rate limits). `force_backfill` for manual trigger.
Stats-tracked. Wired by gateway `pipeline_initializer`.

## Cross-cutting / notable findings (see CONNECTIONS.md)

1. **Subsystem 8 feeds Subsystem 7 (and vice-versa).** `core_manager.process_message` builds the
   `MessagePipeline` and the `MessageContext`, wiring the whole act DAG (the retrieval it passes is this
   subsystem's `ConversationContextBuilder`). Meanwhile Subsystem-7's `MemoryWriteStage` calls
   `perceive_message`/`extract_facts_from_message`/`detect_contradictions` **back into this subsystem** —
   a genuine act↔ingest entanglement. This is the canonical entry path (Phase 4 must confirm the chain
   gateway → core_manager → pipeline).
2. **CONNECTIONS G confirmed at the source:** `core_manager` constructs `ConversationDynamicsEngine` +
   `UserAffectEngine` and hands both into `MessagePipeline.build(...)` — the physics/affect state that act
   stages read.
3. **CONNECTIONS H resolved:** the canonical `MentionTranslator` lives here (`d4_3_mention_translator`).
   The d1_3 `core_voice` copy is the un-referenced duplicate.
4. **CONNECTIONS F complement:** `detect_contradictions` lazily imports `BayesianBeliefEngine` from d1_3
   and both the legacy message_process and act MemoryWriteStage write facts via `belief_engine.store_fact` —
   the d1_1→d1_3 lazy reach-in.
5. **Two intake paths:** the live one is `EnhancedMessageManagerV3.process_message` (pipeline-fed);
   `message_process.py`'s `self`-bound functions are the legacy batch path it superseded (same file calls
   methods it doesn't define — mixed-in/legacy). **Phase-4 dedup candidate.**
6. **Two sentiment tools:** core_manager & message_process use **vaderSentiment** (`SentimentIntensityAnalyzer`
   imported at module top); Subsystem-7 `MemoryWriteStage` tried **nltk** first with a vader fallback. Same
   conceptual analyzer, two library locations — flag for consistency.
7. **Visual is a separate store:** `VisualMemorySystem` uses its own `visual_memory` Qdrant collection
   (CLIP, dim 512), distinct from the main memory collection; and `analyze_image` is deprecated in favor of
   the VLM.
8. **Background/async fan-out:** image descriptions (semaphore-capped vision), correction learning, batch
   flush scheduling, and the dual crawler loops all run as background tasks around the synchronous
   `pipeline.process(ctx)`.

## What's NOT here
- The act pipeline/response stages (`d2_1`, Subsystem 7) — built and driven from `core_manager` here.
- The personality/response-generation brains (`d2_5` + `d2_3 perceive`, Subsystem 6) — `BotPersonality`,
  `ConversationAnalyzer`, `PersonalityState`, `get_response_natural` are *used* here.
- The persistent memory (`d2_4`, Subsystem 5) — `QdrantMemorySystem` is *consumed* here.
- The d1_3 dynamics/affect engines — constructed here from d1_3 (CONNECTIONS G), not owned here.