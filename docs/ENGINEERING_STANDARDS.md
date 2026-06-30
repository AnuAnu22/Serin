# Serin: Engineering Standards

This document complements `CODING_GUIDELINES.md`. That file governs how Serin
*behaves*. This file governs how the *code* is organized, so the project stays
debuggable by a beginner as the cognitive architecture (memory, beliefs,
relationships, personality state) keeps growing. Every future session — human
or AI — reads this before adding a feature.

---

## 1. Why this exists

Twice now, the same failure happened: a cleanup pass consolidated duplicate
files, and within a few commits afterward, new duplicates and a new god
object reappeared (`qdrant.py` is now 1,896 lines holding vector memory,
fact storage, AND belief state machine logic together; `voice/bridge.py` and
`voice/rust_voice_bridge.py` are duplicate files again). This isn't carelessness
— it's that there was no rule saying "this domain concept gets its own file,"
so the path of least resistance is always "add it to the file that already
has similar stuff in it." This document is that rule, made explicit and
checkable.

---

## 2. The structure must mirror the vision, not just the code's history

Serin's vision document defines five distinct memory systems (Working,
Episodic, Evidence, Social, Beliefs) and a Perception → Understanding →
Memory → Beliefs → Goals → Response pipeline. **The folder structure must
make these boundaries visible**, the same way the messaging pipeline's
`stages/` folder made each pipeline step a separate, findable file.

Target structure for the cognitive layer (this is the next restructure, not
yet done — `qdrant.py` currently mixes all of this):

```
serin/
├── cognition/
│   ├── __init__.py
│   ├── perception.py        # message → speech act, evidence blocks, claims
│   ├── understanding.py     # claims + evidence → derived facts
│   └── reasoning.py         # belief revision policy (when does PENDING→SUPPORTED happen)
│
├── memory/
│   ├── __init__.py
│   ├── store.py             # the actual Qdrant/SQLite connection — I/O only, no domain logic
│   ├── working.py           # recent conversation buffer
│   ├── episodic.py          # events/experiences
│   ├── evidence.py          # observed facts: boards, urls, code, quotes
│   ├── social.py            # per-user relationship data
│   └── beliefs.py           # belief state machine: PENDING/SUPPORTED/CONTESTED/SUPERSEDED
│
├── personality/
│   └── state.py             # energy, engagement, confidence, curiosity, mood — the "is", not the "sounds like"
```

**Rule:** if you're adding a new field or function to `qdrant.py` and it's
about *beliefs* or *facts* rather than *the database connection itself*, it
goes in `memory/beliefs.py` or `cognition/understanding.py`, not in
`qdrant.py`. `qdrant.py` (or its replacement `memory/store.py`) should only
know how to talk to Qdrant — it shouldn't know what a belief *means*.

This isn't busywork — it's what makes the vision's promise ("a person joining
months later thinks this is a real member") actually debuggable. If Serin
gives a weird answer about who won a game, you should be able to go straight
to `cognition/understanding.py` and `memory/beliefs.py` — not grep a
2,000-line file for the relevant 80 lines.

---

## 3. Hard limits (mechanical, not judgment calls)

These are checked, not vibes:

- **No file over ~500 lines.** If a file crosses this, it's doing more than
  one job — split it along the domain boundary, not arbitrarily. (`qdrant.py`
  at 1,896 lines is the current violation; splitting it per Section 2 is the
  fix.)
- **One concept, one file.** "Belief state machine" is one file. "Evidence
  classification" is one file. If a docstring needs the word "and" to
  describe what a file does, it's two files.
- **No file may exist twice under different names.** Before creating a new
  file, `grep` the repo for similar existing names/content. This is the
  single rule that would have prevented every duplicate-pair bug found in
  this project so far. A pre-commit hook (Section 5) enforces this
  mechanically going forward, not just by remembering to check.
- **I/O and domain logic are separate files.** `memory/store.py` talks to
  Qdrant. `memory/beliefs.py` decides what a belief *is*. Mixing these is
  what makes `qdrant.py` unreadable today — you can't find the belief logic
  because it's interleaved with connection-handling code.

---

## 4. Git workflow

Right now everything lands as direct commits to `main` with messages like
"Phase 2: belief state machine, evidence classification, ResponsePlannerStage,
intent tracking" — three unrelated features in one commit. That makes it
impossible to `git bisect` a regression or revert just the broken part.

Going forward:

- **One concern per commit.** "Add belief state machine" and "Add evidence
  classification" are two commits, even if written in the same session. If
  you can't summarize a commit in one sentence without "and," split it.
- **Conventional prefixes**, consistent with what's already mostly in use:
  `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`, `test:`. This makes
  `git log --oneline` itself a readable changelog.
- **Every commit that changes behavior must mention test status in the
  message body** — e.g. "Tests: pytest tests/ -q → 44 passed, 0 failed."
  This is cheap and makes the history self-auditing instead of requiring
  someone to re-run things to find out if a given commit was ever verified.
- **Feature branches for anything multi-commit.** A whole new subsystem (like
  the cognitive architecture work) should land on `feature/cognition-layer`
  and merge via a single reviewable diff, not as 3 sequential commits
  straight to `main` where a partial failure halfway through is now live.
- **No commit may introduce a duplicate file.** Covered mechanically below.

---

## 5. Pre-commit checks (automated, not memory-dependent)

Add `.git/hooks/pre-commit` (or a `scripts/check.sh` run manually until you
set up the hook) that runs before anything is allowed to commit:

```bash
#!/bin/bash
set -e

echo "Checking for duplicate-content files..."
python3 scripts/find_duplicate_files.py --fail-on-match

echo "Checking for files over 500 lines..."
find . -name "*.py" -not -path "./.git/*" -not -path "*/__pycache__/*" \
  -exec wc -l {} \; | awk '$1 > 500 {print; fail=1} END {exit fail}'

echo "Checking imports..."
python3 -c "import serin.core.config, serin.core.logger, serin.memory.qdrant, serin.messaging.pipeline, serin.control_panel.server"

echo "Running tests..."
DISCORD_TOKEN=test pytest tests/ -m "not integration" -q

echo "All checks passed."
```

`scripts/find_duplicate_files.py` is a ~15 line script: walk all `.py`
files, hash content (ignoring whitespace/comments), flag any two files with
matching hashes. This single script is what would have caught every
duplicate-pair bug across all three rounds of this project, automatically,
before it ever reached a commit — instead of relying on an external audit
to notice months later.

---

## 6. Documentation that stays true

`ARCHITECTURE.md` should be a living map, not a one-time snapshot. The rule:
**any commit that adds a new top-level module under `serin/` must update
`ARCHITECTURE.md` in the same commit.** If `cognition/` gets created per
Section 2, that's the commit that also adds a paragraph to
`ARCHITECTURE.md` explaining what it's for. A README that's accurate the day
it's written and wrong three months later is worse than no README — it
actively misleads the next person (or AI) trying to orient themselves.

---

## 7. The actual next step

This document describes the target. The current state (`qdrant.py` at 1,896
lines housing memory + facts + beliefs together) is the gap. The next
engineering session — separate from any new feature work — should be:

1. Run `scripts/find_duplicate_files.py` and resolve every hit (start with
   `voice/bridge.py`/`voice/rust_voice_bridge.py` and
   `voice/processor.py`/`voice/audio_stream_processor.py`, both confirmed
   duplicates as of this writing).
2. Split `qdrant.py` into `memory/store.py` (I/O only) + `memory/beliefs.py`
   + `memory/evidence.py`, per Section 2. Zero behavior change — this is a
   structural move, exactly like the original Phase 1/2 restructure, not a
   logic change. Same "zero behavior change" rule applies: verify with the
   existing test suite before and after, not just "it imports."
3. Add the pre-commit script from Section 5 so this doesn't recur a third
   time.

Do not bundle this with new feature work. Structural commits and feature
commits are different concerns — mixing them is exactly how the last two
rounds ended up needing an external audit to untangle what changed.
