# Serin: The Architecture Law

This is not a style guide. This is not a set of best practices. This is
the physical law of the Serin codebase. Every file, folder, import, and
line of code is governed by these rules without exception, without
interpretation, and without appeal. If a rule feels inconvenient, the code
changes. The rule does not.

A person with two days of Python experience must be able to open this
repository, navigate to any specific line of code, and understand exactly
where they are — without grep, without asking, without thinking. The
structure must be so rigid and so consistent that the correct location of
any piece of code is the only location that could ever have been chosen.
Not the most likely location. The only location.

---

## The Physical Shape of the Repository

The repository root contains exactly these items and nothing else:

```
Serin/
├── discord_bot.py        # 3-line entry point: imports main, calls main()
├── hot_reloader.py       # 3-line entry point: imports and runs the reloader
├── pyproject.toml        # Project metadata and dependencies
├── README.md             # How to run the bot, nothing more
├── serin/                # All source code lives here, nowhere else
├── tests/                # All tests live here, mirroring serin/'s structure
└── scripts/              # Automation scripts: law checkers, deploy helpers
```

Nothing else belongs at the root. No `.py` source files other than the two
entry points. No configuration files other than `pyproject.toml`. No
documentation other than `README.md`. If something doesn't fit one of
these seven slots, it goes inside `serin/`, `tests/`, or `scripts/`. There
is no eighth slot.

The two entry point files (`discord_bot.py`, `hot_reloader.py`) exist at
root for one reason only: so a person running the bot types
`uv run discord_bot.py` and it works. They contain no logic. A 3-line
entry point looks like this and nothing more:

```python
"""Entry point — starts the Serin Discord bot."""
from serin.gateway.discord.bot import main
if __name__ == "__main__":
    main()
```

---

## Rule 1 — The 5/5 Horizon

**No directory contains more than 5 items total.** Files and subdirectories
are counted together. A directory with 3 files and 2 subdirectories has 5
items and is full. A directory with 4 files and 1 subdirectory is also
full. A directory with 5 subdirectories and 0 files is full.

When you need a 6th item, you do not add it. You stop and ask: which 2 or
3 of the existing 5 items share a deeper underlying concern that hasn't
been named yet? That unnamed concern becomes a new subdirectory. The items
that belong to it move inside it. The count drops. Now there is room.

If you cannot find a grouping that makes logical sense, your items are
wrong — not the rule. You have listed tasks, not concepts. Read the items
again and find what two of them are really doing the same deeper job.

**Why 5:** The human brain holds 5 items in working memory without effort.
At 6, scanning begins. This limit ensures that at every single point in
the codebase, the local view never changes. You open a folder and see 5
things or fewer, always, whether you are at depth 1 or depth 9.

---

## Rule 2 — The 500-Line Ceiling

**No `.py` file contains more than 500 lines.** Blank lines and comments
count. Docstrings count. At 501 lines, the file must become a folder.

### How a file becomes a folder

`3-2_belief-revise.py` at 501 lines becomes the folder `3-2_belief-revise/`.
Inside that folder, you create new files at depth 4, each handling one
real sub-concern of the original. The original file is deleted entirely —
not kept as a redirect, not kept as an `__init__.py` that re-exports
everything. Deleted.

Every importer of the original file must be updated to import from the
specific new file that now owns what it needs. If ten files imported
`from serin.pipeline.act.belief_revise import update_belief`, each of
those ten files now imports from whichever depth-4 file owns
`update_belief`. You find them with:
```bash
grep -rn "belief_revise" --include="*.py" .
```
You fix every result. You verify with the same grep after. Zero results
means done.

### The only exception: `__init__.py`

Each folder may contain one `__init__.py`. It must be empty or contain
only `# intentionally empty`. It exists to make the folder a Python
package. It contains no logic, no imports, no re-exports. Its line count
does not factor into the 500-line ceiling because it has no lines.

### No redirect files, ever

A redirect file is a file whose only content is importing from somewhere
else and re-exporting it. Example of what is permanently forbidden:
```python
# THIS IS ILLEGAL — redirect file
from serin.pipeline.remember.core.store import QdrantMemorySystem
```
This pattern is forbidden even during migrations. If you are moving a file
and need to update importers, you update the importers. You do not create
a redirect to avoid updating them. A redirect file is a lie — it tells the
person reading it that the logic lives here, when it lives somewhere else.

---

## Rule 3 — The Depth-Sequence Coordinate

**Every file and folder is named with this exact pattern:**

```
{Depth}-{Sequence}_{Word1}-{Word2}
```

- **Depth**: A single digit (1–9) representing how many folders deep this
  item is from the `serin/` root. `serin/` itself is depth 0. Its direct
  children are depth 1. Their children are depth 2. And so on.
- **Sequence**: A single digit (1–5) representing this item's position
  among its siblings, ordered by their role in the system's data flow —
  earliest in the pipeline first, most fundamental first.
- **Word1-Word2**: Exactly two English words separated by a hyphen. The
  first word is a verb or a role noun. The second word is the subject. No
  abbreviations. No acronyms. No implementation details (not `sqlite-db`,
  but `memory-store`). No cute names. No single-word names. No
  three-word names.

**Examples of correct names:**
- `1-1_pipeline/` — depth 1, first item, pipeline stage
- `3-2_belief-revise.py` — depth 3, second item, belief revision
- `4-5_error-base.py` — depth 4, fifth item, base error classes

**Examples of illegal names:**
- `utils.py` — no coordinate, one word, junk drawer
- `2-1_mgr.py` — abbreviation
- `3-3_enhanced-message-manager.py` — three words
- `helpers/` — no coordinate, junk drawer
- `1-2_Gateway/` — capitalized

**The coordinate is not decoration.** A person reading `4-2_belief-revise.py`
knows without opening it: this file is 4 levels deep, it is the second
concern at that level, it handles belief revision. The name contains the
address. You do not need the full path to know where you are.

---

## Rule 4 — The Law of Buoyancy

**The depth of a file is determined by how specific its concern is.**
General concerns float toward depth 1. Specific concerns sink toward
depth 9. There is no judgment involved — you answer one question:

> "How many branches of the codebase need this?"

- **Every branch needs it** → it belongs in `serin/state/` at depth 1.
  Examples: the logger, shared data types, base error classes, constants
  used everywhere.
- **One top-level branch needs it** → it belongs inside that branch at
  depth 2 or deeper. Examples: voice-specific data types belong inside
  `serin/gateway/voice_system/`, not in `serin/state/`.
- **One specific stage of one branch needs it** → it sinks to exactly
  that stage. Examples: BM25 index logic belongs inside
  `serin/pipeline/remember/`, not at the top of the pipeline.

**The practical test for "does this belong in state/?"**
After you write the file, grep for its imports across the whole codebase.
If files from more than one top-level branch (`pipeline/`, `gateway/`,
`ops/`) import it, it belongs in `state/`. If only files from one
top-level branch import it, it belongs inside that branch — not in
`state/`. Move it down.

**There is no "I'm not sure" answer.** If you are unsure, run the grep.
The grep tells you. You do not decide — the import count decides.

---

## Rule 5 — The Up-and-Left Boundary

**A file may only import from:**

1. Files inside its own folder or any subfolder of its own folder
   (its descendants).
2. Files in its parent folder or any ancestor folder up to `serin/`
   (its ancestors).
3. Files in any folder that is a sibling of any of its ancestors
   (its ancestors' siblings) — but only at that sibling's root level,
   not deep into that sibling's children.

**A file may never import from a cousin.** A cousin is any file that
requires you to go UP past your immediate parent and then DOWN into a
different branch.

**The one-sentence test:** Look at the import path. If it goes `../../`
(up two levels) and then into a different directory name than the one you
just left, it is a cousin import and it is illegal.

**Concrete examples with the Serin tree:**

```
serin/
├── pipeline/       ← depth 1
│   └── remember/   ← depth 2
│       └── store.py ← depth 3
├── gateway/        ← depth 1
│   └── discord/    ← depth 2
│       └── bot.py  ← depth 3
└── state/          ← depth 1
    └── logger.py   ← depth 2
```

- `bot.py` importing `logger.py` → **LEGAL**. `state/` is a depth-1
  folder. All depth-1 folders are ancestors of every file in the repo.
  This is going up, not across.
- `bot.py` importing `store.py` → **ILLEGAL**. `store.py` is inside
  `pipeline/remember/`, a cousin branch. `bot.py` has no relationship
  to `pipeline/remember/` in the ancestry chain. If `bot.py` needs
  something from `store.py`, the shared thing must be moved to `state/`.
- `store.py` importing `logger.py` → **LEGAL**. Same reason as above.
- `store.py` importing `bot.py` → **ILLEGAL**. `bot.py` is a descendant
  of `gateway/`, a cousin branch.

**What to do when you discover a cousin import:**
Do not change the import path to make it work. Ask: should the imported
thing be in `state/` because multiple branches need it? If yes, move it
to `state/` and update all importers. If only one branch needs it, the
importer is in the wrong branch and needs to be restructured, not patched.
There is no third option.

---

## Rule 6 — Internal File Anatomy

**Every Python file follows this exact section order:**

```python
"""One sentence. What this file does."""

# --- Imports ---
# (standard library, then third-party, then serin.state, then serin siblings)

# --- Types ---
# (dataclasses, TypedDicts, NamedTuples, Enums defined in this file)

# --- Constants ---
# (module-level constants: no magic numbers anywhere else in the file)

# --- Entry ---
# (the one public function or class this file exposes — the "front door")

# --- Core ---
# (the main logic: functions and methods called by Entry)

# --- Helpers ---
# (private functions called only by Core, prefixed with _)

# --- Errors ---
# (exception classes defined in this file, if any)
```

Every section header must be present in every file, even if the section
is empty. An empty section looks like:
```python
# --- Types ---
# (none)
```

**Why every section must exist:** A person who has read three files in
this codebase knows where to look for error handling in the fourth without
scrolling. The section is always there. It is always in that position. If
the section is empty, the person confirms it in one second and moves on.
If the section is missing, the person wonders if the convention applies
here, checks surrounding files for comparison, and loses two minutes. The
empty section costs nothing. The missing section costs trust.

**The one public entry point rule:** Every file exposes exactly one
primary public symbol — the thing in the `# --- Entry ---` section. It
is the function or class that importers call. Everything else is Core or
Helper. If a file has three functions that all feel like "public API,"
the file is doing three jobs and must be split into three files.

---

## Rule 7 — No Junk Drawers

**These folder names are permanently banned:** `utils/`, `helpers/`,
`common/`, `misc/`, `shared/`, `tools/`, `lib/`, `core/` (when used as
a catch-all).

A junk drawer is any folder whose contents cannot be described in one
sentence that doesn't use the word "various," "miscellaneous," "shared,"
or "common." If you cannot say exactly what a folder contains without
those words, the folder is a junk drawer.

**What to do instead of creating a junk drawer:**
For each file you would have put in `utils/`, ask: which top-level branch
actually uses this? If one branch uses it, it sinks into that branch. If
multiple branches use it, it belongs in `serin/state/`. Run the import
grep. The answer is always one of those two options.

The ban on `core/` as a catch-all is specific: `core/` is legal as a
subfolder name if it means "the core logic of this specific parent folder"
— e.g., `serin/pipeline/remember/core/` containing the main store logic
for the remember stage. It is illegal as a depth-1 folder named
`serin/core/` that contains "foundational stuff" — that is `serin/state/`.

---

## The Top-Level Structure (Fixed, Not Negotiable)

`serin/` contains exactly these five items:

```
serin/
├── pipeline/    # The message lifecycle: ingest → perceive → think → remember → act
├── gateway/     # I/O boundaries: Discord, voice, text, media, model adapters
├── state/       # General truths used by 2+ top-level branches: types, logger, constants
├── config/      # Environment variables, secrets, bot settings
└── ops/         # Operational machinery: deployment, law checkers, hot reload, backup
```

These five names are fixed. They do not change. A new top-level concern
does not get a sixth folder — it fits into one of these five or it
does not exist yet. If you genuinely cannot fit a new top-level concern
into any of these five, you stop and discuss it before creating anything.
You do not create a sixth folder unilaterally.

**What lives where, resolved once:**

| Concept | Location | Why |
|---|---|---|
| Logger | `serin/state/` | Every branch imports it |
| Base exception class | `serin/state/` | Every branch raises/catches it |
| Shared dataclasses (MessageContext, etc.) | `serin/state/` | Pipeline and gateway both use them |
| DatabaseProtector | `serin/state/` | Gateway, pipeline, and ops all need it at startup |
| Discord client setup | `serin/gateway/discord/` | Only the gateway owns the Discord connection |
| Voice bridge (Rust) | `serin/gateway/voice_system/` | Only the gateway owns the voice connection |
| LLM model connectors | `serin/gateway/model_system/` | Only the gateway owns the model connection |
| Qdrant memory store | `serin/pipeline/remember/` | Only the remember stage writes/reads memories |
| Belief state machine | `serin/pipeline/act/believe/` | Only the act stage manages beliefs |
| Evidence store | `serin/pipeline/act/believe/` | Used exclusively by the believe sub-stage |
| Hot reloader | `serin/ops/` | Operational tooling, not domain logic |
| Database backup | `serin/ops/` | Operational tooling, not domain logic |
| Law check scripts | `scripts/law/` | Not source code, not tests — automation |

If a concept is not in this table, apply Rule 4 (run the import grep,
let the count decide) and add it to this table before committing.

---

## Verification

These checks run on every commit via `.git/hooks/pre-commit`. A commit
that fails any check is rejected. There are no warnings, only pass or
fail.

```bash
#!/usr/bin/env bash
set -e
python3 scripts/law/check_structure.py   # Rules 1, 2, 3
python3 scripts/law/check_imports.py     # Rule 5
DISCORD_TOKEN=test pytest tests/ --ignore=tests/test_vision.py -m "not integration" -q
```

`check_structure.py` fails if:
- Any directory contains more than 5 items
- Any `.py` file (outside `tests/`) exceeds 500 lines
- Any file or folder name does not match `{digit}-{digit}_{word}-{word}.py`
  or the exact root exceptions (`discord_bot.py`, `hot_reloader.py`,
  `pyproject.toml`, `README.md`, `__init__.py`, `conftest.py`)

`check_imports.py` fails if:
- Any import goes up two or more levels and then down into a different
  branch (cousin import)
- Any file in `serin/gateway/` imports from `serin/pipeline/` or vice
  versa, except through `serin/state/`
- Any file in `serin/ops/` is imported by any file in `serin/pipeline/`
  or `serin/gateway/`

These are not suggestions. A green pre-commit hook is the definition of
"this follows the Law." A commit message that says "follows the Law"
without a green hook is not evidence of anything.
