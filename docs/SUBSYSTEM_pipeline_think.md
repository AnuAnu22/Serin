# SUBSYSTEM: pipeline_think — personality + response generation (d1_1 d2_5 + d2_3)

Checklist: 11/11 files read. Status: DRAFT (wip). Finalize name: `SUBSYSTEM_pipeline_think.md`.

Roots: `serin/d1_1_pipeline_flow/d2_5_flow_think/` (6 files) + `serin/d1_1_pipeline_flow/d2_3_flow_perceive/` (5 files).

## Scope & role in the system

Two sibling "personality/thinking" subfolders of the pipeline layer:

- **`d2_5_flow_think`** — the RESPONSE-GENERATION personality side. Holds the humanization
  engine (fillers + typos), the persistent `PersonalityState`, the big `response_generator.py`
  (the direct LLM chat path), and `ResponsePlannerStage` (a pipeline stage that turns beliefs+
  facts+intent into a binding response plan).
- **`d2_3_flow_perceive`** — a "perceive/think" folder of helper brains (active search,
  bot personality preferences, conversation analyzer, topic fatigue). Wiring is mixed:
  `BotPersonality` + `ConversationAnalyzer` are used by the ingest core; `ActiveSearch` +
  `TopicFatigue` are DEAD.

NOTE (corrects earlier plan assumption): `llm_call` and `prompt_assembly` do NOT live here —
they are in `d2_1_flow_act` (Subsystem 7). This subsystem supplies the personality/thinking
helpers those stages consume.

## Files (d2_5_flow_think)

### d3_1_think_personality/d4_1_personality_humanization.py — LIVE
Two "make the bot sound human" engines, plus module-level convenience functions.
- `ConversationalFillers` — injects filler words ("hmm", "you know", "tbh", ...) at an 8% base
  rate, scaled by energy; deliberately SKIPS concession/agreement sentences
  (`CONCESSION_PATTERNS`) so it never dilutes a clean "you're right". Uses `secrets` RNG.
- `RealisticTypos` — 3% base rate (up to 5% when energetic), max ONE typo/message, from curated
  dictionaries (apostrophe drops, adjacent-key transpositions, common misspellings); never on
  protected words (commands/names) and never on important messages.
- `get_filler_engine()/get_typo_engine()` — module-level singletons; `add_conversational_fillers`
  / `add_realistic_typos` convenience wrappers. Consumed by `response_generator.py`.

### d3_1_think_personality/d4_2_personality_state.py — LIVE, multi-subsystem
`PersonalityState` — rolling energy/sass/engagement (each 0..1) + a bounded 500-sample
`deque` mood history for the control panel. Key methods:
- `update_from_conversation(mood, user_traits, time_of_day)` — time-of-day energy curve, mood
  matching, trait-driven sass, decay-to-baseline after 1h; persists to SQLite every 10th update.
- `save_to_db/load_from_db` — creates `personality_state` + `personality_history` tables.
- `get_tone_modifier(user_id=None)` — produces the LLM tone-guidance string ("Be energetic and
  punchy"...). Without a user it reads the global default mood. With a user it reads that
  relationship's per-user mood vector instead.
- **Per-relationship mood / emotional persistence** (CODING_GUIDELINES §4):
  `update_from_conversation(..., user_id, relationship)` updates a **per-user** vector persisted
  in the `user_mood_state` table (Subsystem 5 schema) rather than the shared global mood; a new
  user is seeded from the global default, so a mood set with one user never bleeds into another.
  `relationship` is one of `stranger`/`enemy`/`friend`/`acquaintance`, derived by
  `relationship_category(valence, familiarity)` in the d1_3 affect engine and applied as a
  write-time bias (enemy → higher sass/lower engagement; friend → higher engagement).
  The global fields + `_history` remain the default mood the control-panel mood widget charts.
- `set_mood_preset(preset)` — atomic control-panel mood override (high_energy/neutral/sass/chill);
  returns False for unknown preset so the route can 400. The docstring explicitly explains WHY the
  update must be atomic (avoids mid-flight pipeline reads seeing half-applied mood).
- `get_history/to_dict` — panel live-mood widget data.
Multi-subsystem: used by d1_1 act stage `d4_4_personality_stage`, ingest `core_manager`, AND
the voice gateway (`system_output`, `voice_behavior`).

### d3_1_think_personality/__init__.py — `# intentionally empty`

### d3_3_response_generator.py — LIVE (the direct LLM chat path; PyO3 seam)
The classic "natural response" generator. Module-global connector holders `llama`/`vision_llama`/
`discord_client` (poked via serin_di wrappers — CONNECTIONS I).
- `initialize_llama()` — builds the ModelInterface via `get_model_connector()` (d1_3 model_system);
  optionally initializes a separate SmolVLM vision connector when `config.LLM_SUPPORTS_VISION`.
- `get_response_natural(messages, context, tone_modifier, personality_state, message_complexity, is_instruction)` —
  builds system/user messages, handles BOTH pipeline (`{"role":...}`) and legacy
  (`{"user_name":...}`) message formats, image support (main-LLM vision vs SmolVLM fallback vs
  "[Image attached]"), picks token budgets + `chat_template_kwargs.enable_thinking` for
  thinking-capable models (`_should_use_thinking`), logs PROMPT_DEBUG, then:
  `filter_thinking` (d1_3 thinking_filter, PyO3) → `clean_response` (special tokens, name prefixes,
  mention strip, 400-char natural truncation) → `apply_natural_variations` →
  `add_conversational_fillers` → `add_realistic_typos`.
- `apply_natural_variations()` — **PyO3 seam at line 352: `import serin_core` →
  `apply_contractions`** with a Python regex fallback dict (→ CONNECTIONS D). Also 30% first-letter
  lowercase, 20% dropped final period, occasional "lol/haha".
- `build_natural_system_prompt()` — the big Serin persona system prompt (used by prompt_assembly
  in Subsystem 7). `build_instruction_system_prompt()` — strict "obey Rin, drop persona" prompt.
- Failure fallback: "brain.exe stopped working" / "uh what" / "lost my train of thought".
Consumed by serin_di, `core_manager`, `message_process` (Subsystem 8).

### d3_4_response_planner.py — LIVE (pipeline stage)
`ResponsePlannerStage(PipelineStage)` — **beliefs are binding, not advisory.** Reads
`ctx.beliefs` + `_detect_user_claim(raw_content)` + `ctx.intent`, and produces
`ctx.response_plan` = `{stance, confidence, constraints, contradictions, allowed_tones,
forbidden_moves}`. Logic: SUPPORTED belief conf>=0.7 → strong stance + constraint; user claim
checked for negation/agreement keywords to set disagree/agree; CONTESTED → uncertain + tentative
tone; SUPERSEDED → forbidden move "asserting X". Intent→strategy table maps intent to base stance +
strength bonus. Wired into runners_pipeline (Subsystem 7); the panel `server_state.py` reads the
resulting plan. Uses `MessageContext` (d1_3) as its envelope.

### d2_5_flow_think/__init__.py — empty

## Files (d2_3_flow_perceive)

### d3_1_active_search.py — DEAD (zero importers)
`ActiveSearch` — an "internal monologue" LLM call that decides whether to search memory and
generates a query. Two-stage: `_passes_heuristics` (fast path keyword/length gate), then an LLM
JSON decision (`analyze_need_to_search`, temp 0.1, stop at `}`) supporting query REFINEMENT when
given previous results. `_parse_decision` regex-extracts the JSON. Despite being thorough, nothing
in serin/ or tests imports it — the pipeline's retrieval is driven elsewhere.

### d3_2_bot_personality.py — LIVE
`BotPersonality(db_path="./bot_data/bot_data.db")` — a SEPARATE SQLite personality DB
(`bot_preferences` + `bot_opinions` tables) with hardcoded defaults (music/games/food/activities/
topics with love/like/neutral/dislike/hate + intensity + reason). `get_preference`, `get_opinion`,
`can_disagree`, `get_personality_context` (renders top loves/likes/dislikes/hates as a natural
sentence block for the prompt). Used by the act `personality_stage` and ingest `core_manager`.
NOTE: this uses its own `bot_data/bot_data.db` path — separate from the core memory `bot_data.db`.

### d3_3_conversation_analyzer.py — LIVE
`ConversationAnalyzer` — multi-message flow analysis: topic detection (simple keyword frequency),
topic-change tracking per channel (`active_topics`/`topic_history`), pattern detection
(back-and-forth / group discussion / questions / exclamations / avg length), conversation
classification (question_answer/dialogue/group_discussion/storytelling/casual_chat), participant
analysis, summary, and `should_acknowledge_topic_change`. Used by ingest `core_manager`.

### d3_4_topic_fatigue.py — DEAD (zero importers)
`TopicFatigue` — tracks per-channel topic mention timestamps; fatigue 0..0.9 based on 5/10+
mentions within a 10-min window; `apply_fatigue_to_personality` lowers energy/engagement;
`get_fatigue_context_note` emits a prompt note. Module-level `get_fatigue_tracker`/
`track_topic`/`get_topic_fatigue`. Nothing imports it (the personality logic in d4_2/d4_4 is used
instead).

### d2_3_flow_perceive/__init__.py — empty

## Cross-cutting / notable findings (see CONNECTIONS.md)

1. **Split of "think":** the personality/response brains live in `d2_5`; the LLM call + prompt
   assembly live in `d2_1` (Subsystem 7). `get_response_natural` is imported by Subsystem 8 files
   (`core_manager`, `message_process`) too — so the think layer feeds both act and ingest paths.
2. **Two DEAD perceive modules:** `ActiveSearch` and `TopicFatigue` are fully unreferenced —
   ambitious scaffolding that never got wired (the "internal monologue search" idea and the
   "bored of a topic" idea). `ConversationAnalyzer` + `BotPersonality` ARE live (ingest core).
3. **PyO3 seams here:** `apply_contractions` (response_generator:352, CONNECTIONS D); also
   `filter_thinking` is imported from d1_3 thinking_filter (itself a PyO3 seam).
4. **`PersonalityState` is genuinely multi-subsystem:** act stage, ingest core, and the VOICE
   gateway (system_output, voice_behavior) all touch it — the same object spans d1_1 and d1_2.
5. **`ResponsePlannerStage` is the belief-constraint bridge:** it converts the (d1_3 Bayesian)
   belief state machine (SUPPORTED/CONTESTED/SUPERSEDED/UNKNOWN) into binding prompt constraints
   — this is the concrete mechanism by which the d1_3 belief engine influences output. The panel
   (`server_state.py`) reads the plan for observability.
6. **`BotPersonality` has a second SQLite DB** (`bot_data/bot_data.db`) with its own schema —
   separate from the core memory `bot_data.db`. Watch for path collisions in Phase 4.

## What's NOT here
- `llm_call`, `prompt_assembly` (d2_1 pipeline_act, Subsystem 7) — the actual LLM call + prompt build.
- `thinking_filter` implementation (d1_3 model_system) — only imported here.
- The `personality_stage` act stage (Subsystem 7) that consumes `PersonalityState`/`BotPersonality`.