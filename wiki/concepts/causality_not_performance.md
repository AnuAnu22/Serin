---
type: concept
tags: [vision, philosophy, design]
created: 2026-08-16
updated: 2026-08-16
sources: [docs/SERIN_VISION.md, docs/superpowers/specs/2026-08-10-response-generation-critique.md, docs/CODING_GUIDELINES.md]
status: seed
---

# Causality, Not Performance

## What it is

The Prime Directive mechanism of the Serin vision: **Serin's behavior must be caused by real,
persistent, accumulated state — never selected fresh each time because it would sound
appropriate.** A human's warmth toward a friend isn't chosen in the moment; it's downstream of an
actual history. A performance drifts back to a neutral default the instant nothing is telling it
to perform; real state persists, drifts under its own logic, and holds up when pushed.

## The test for any new feature

- ✅ Read the actual accumulated state for this specific relationship and let output be a
  consequence of it.
- ❌ "Roll a die and pick a variation" or "describe the desired mood in the prompt and hope the
  model complies."

## Where it shows up

- [[conversation_dynamics_engine]] — reply/react/ignore + timing are consequences of momentum,
  familiarity, valence.
- [[bayesian_beliefs]] — belief strength is accumulated evidence, not a lookup.
- `AffectEngine` — per-user valence/familiarity with decay; impressions injected into the prompt.
- `PersonalityState` — per-relationship mood vectors (emotional persistence: not angry at one
  person then happy at the next because the prompt changed).

## What it condemns (from the 2026-08-10 critique)

The response-generation critique argues the current code still inverts the vision: a *spec* of a
persona instead of a voice, binary-thresholded mood, five-bucket affect, **post-hoc RNG
humanization** (typos/fillers manufactured at fixed rates — a machine pretending to be imperfect),
and scripted fallbacks (`"brain.exe stopped working"`) that betray the illusion exactly at an
error. The right shape: build the voice in generation, shaped continuously by mood and affect;
failure that sounds like a person drawing a blank, not a script firing. (See [[known_debt]].)

## See also

[[message_flow]] · [[conversation_dynamics_engine]] · [[index]]
