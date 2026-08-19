# Serin Wiki — Log

Append-only chronology (`## [YYYY-MM-DD] <op> | <title>`). Latest first.

## [2026-08-16] scaffold | Serin Project Wiki
Created the wiki at `wiki/`: schema (SCHEMA.md), index, log, five overviews
(architecture, message_flow, voice_flow, testing, known_debt), seven entity pages
(message_pipeline, conversation_dynamics_engine, qdrant_memory_system, serin_di,
enhanced_message_manager_v3, rust_voice_bridge, bot_config), and five concept pages
(bayesian_beliefs, the_law_rule5, dave_receive, causality_not_performance, gateway_isolation).
All seed pages distilled from a full read of `docs/` (ARCHITECTURE, CONNECTIONS, THE_LAW,
SERIN_VISION, SUBSYSTEM_*, the voice wiki, superpowers) on 2026-08-16. No sources category yet —
first INGEST pass should add the major docs as `source` pages.
## [2026-08-18] query | Vision-to-Code Fix Plan
Filed `wiki/queries/2026-08-18_vision_to_code_fix_plan.md` after implementing the approved
fix plan (docs/SERIN_VISION.md "Operational Definitions" now governs). Removed the RNG
humanizer module (`d4_1_personality_humanization.py` deleted), made `can_disagree` and
`_express_unknown` deterministic, rewrote `detect_topic_stance` (textual-order markers +
pronoun referents), fixed planner M3/M4, added SendStage latency floor, replaced scripted
fallbacks, graduated `_affect_context` familiarity ramp, and added semgrep rules
`no-performative-randomness` + `no-mood-directive`. Verified: ruff/mypy clean, 7 semgrep
rules 0 findings, targeted suites green, full suite 623 passed (2 pre-existing documented
failures: A1 affect-engine event-loop flake; semgrep test blocked by sandbox read-only
`~/.semgrep` — passes when HOME is writable).