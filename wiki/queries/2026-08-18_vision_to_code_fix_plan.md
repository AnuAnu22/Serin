---
type: query
tags: [vision, causality, fixes, plan]
created: 2026-08-18
updated: 2026-08-18
sources: [docs/SERIN_VISION.md, docs/superpowers/specs/2026-08-10-response-generation-critique.md]
status: live
---

# Vision-to-Code Fix Plan (2026-08-18)

## What it is

Filed analysis: how the SERIN vision ("causality, not performance") was being
violated in code, and the approved fix plan. Implemented same-day. This page
records what was wrong, what changed, and the enforcement added so it stays
fixed. See also [[causality_not_performance]].

## The violations found

| # | Where | Violation |
|---|---|---|
| 1 | `serin/d1_1_pipeline_flow/d2_5_flow_think/d3_1_think_personality/d4_1_personality_humanization.py` | Post-hoc RNG "humanization": `_rand()`-driven typos/fillers/case-drops inserted after generation — imperfection as a die roll, not a state consequence. |
| 2 | `.../d4_2_personality_state.py` `_build_tone_modifier` + `d3_3_response_generator.py` `resolve_system_prompt` | Mood directive: threshold cliffs (`>0.65`/`<0.35`) with a silent dead middle band, appended as "Current mood: ..." — describing the mood instead of causing it. |
| 3 | `d3_2_bot_personality.py` `can_disagree` | Die-roll disagreement: `_rand() < (0.35 + 0.5*confidence)` |
| 4 | `d3_2_bot_personality.py` `detect_topic_stance` | Marker-list order beat textual order ("i like gaming but hate politics" -> `(politics, hate)`); no "it/that" referent resolution. |
| 5 | `d3_4_response_planner.py` | Forced agreement: `if not constraints: stance = "agree"`; contradictions flagged on agreements too (M3/M4). |
| 6 | `d5_2_dispatch_send.py` | Instant reply: `delay = 0.0` for creator override — literally instant. |
| 7 | `d3_3_response_generator.py` | Scripted failure tells: "brain.exe stopped working" trio. |

## The fixes (all landed 2026-08-18)

1. **Humanizer removed.** Module deleted; no post-generation dice. Imperfection
   now downstream of real state (energy/fatigue shaped in the persona).
2. **Continuous tone.** `_build_tone_modifier` maps the whole energy/sass/
   engagement range in graduated bands (no cliffs, no dead zone), phrased as
   Serin's current state; `resolve_system_prompt` no longer appends a
   "Current mood:" label.
3. **Deterministic disagreement.** `can_disagree` returns True on genuine
   directional conflict (state comparison), never a roll; tests updated to
   assert determinism.
4. **Stance fixes.** `detect_topic_stance` scans by first textual occurrence
   and resolves pronouns; planner flags contradictions only on real negation
   and never forces "agree" without a user claim.
5. **Latency floor.** SendStage has `min_send_delay = 0.4` — never literally
   instant, even for the creator override.
6. **Fallbacks.** "brain.exe stopped working" replaced with confused-human
   lines; `_express_unknown` made deterministic (stable character-sum).
7. **Affect ramp.** `_affect_context` graduates with familiarity (stranger
   suppression < 0.1 kept as a deliberate safety guard; muted 0.1-0.5; full
   bands >= 0.5) instead of snapping from empty to "genuinely like".

## Enforcement added

- `.semgrep/rules/no-performative-randomness.yaml` — die rolls in
  personality/mood/affect code.
- `.semgrep/rules/no-mood-directive.yaml` — "Current mood:" / imperative tone
  commands in `serin/`.
- `docs/SERIN_VISION.md` now carries an "Operational Definitions" table
  (banned pattern vs required causality) mapping 1:1 to these rules.

## Verification

- `ruff check serin/` clean; `mypy serin/` clean; 7 semgrep rules, 0 findings.
- Targeted suites green: `tests/test_bot_opinions.py`, `tests/test_relationship_mood.py`,
  `tests/inspector/`, `tests/test_affect_context.py`,
  `tests/pipeline_contracts/test_prompt_assembly.py`.
- Full non-integration suite: 623 passed, 2 pre-existing documented failures
  (A1 affect-engine event-loop flake; semgrep test blocked by sandbox read-only
  `~/.semgrep` — passes when HOME is writable).

Related: [[message_pipeline]], [[conversation_dynamics_engine]], [[bot_config]].