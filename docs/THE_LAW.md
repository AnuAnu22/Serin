# Serin: The Architecture Law

This is not a style guide. This is not a set of best practices. This is the physical law of the Serin codebase. Every file, folder, import, and line of code is governed by these rules without exception, without interpretation, and without appeal. If a rule feels inconvenient, the code changes. The rule does not.

A person with two days of Python experience must be able to open this repository, navigate to any specific line of code, and understand exactly where they are — without grep, without asking, without thinking. The structure must be so rigid and so consistent that the correct location of any piece of code is the only location that could ever have been chosen. Not the most likely location. The only location.

---

## The Physical Shape of the Repository

The repository root is the Dependency Injector. It contains exactly these items and nothing else:

```
Serin/
├── discord_bot.py        # 3-line entry point: loads config/state, injects into serin
├── hot_reloader.py       # 3-line entry point: imports and runs the reloader
├── pyproject.toml        # Project metadata and dependencies
├── README.md             # How to run the bot, nothing more
├── serin/                # All source code lives here, nowhere else
├── tests/                # All tests live here, mirroring serin/'s structure
└── scripts/              # Automation scripts: law checkers, deploy helpers
```

Nothing else belongs at the root. No `.py` source files other than the two entry points. No configuration files other than `pyproject.toml`. No documentation other than `README.md`. If something doesn't fit one of these seven slots, it goes inside `serin/`, `tests/`, or `scripts/`. There is no eighth slot. (This root contains 2 files and 5 folders, perfectly obeying the 5/5 Horizon below).

The two entry point files exist at root for one reason only: so a person running the bot types `uv run discord_bot.py` and it works. They contain no logic. They read environment variables, instantiate the shared state (like the logger), and pass those instances down into `serin/`. A 3-line entry point looks like this and nothing more:

```python
"""Entry point — starts the Serin Discord bot."""
from serin.gateway.discord.bot import main
if __name__ == "__main__":
    main()
```

---

## Rule 1 — The 5/5 Horizon

**No directory contains more than 5 subdirectories, and no directory contains more than 5 files.** The maximum number of items in any directory is 10. A directory with 5 folders and 5 files is full. A directory with 3 files and 2 subdirectories has 5 items and has room for more.

When you need a 6th file or a 6th folder, you do not add it. You stop and ask: which 2 or 3 of the existing items share a deeper underlying concern that hasn't been named yet? That unnamed concern becomes a new subdirectory. The items that belong to it move inside it. The count drops. Now there is room.

If you cannot find a grouping that makes logical sense, your items are wrong — not the rule. You have listed tasks, not concepts. Read the items again and find what two of them are really doing the same deeper job.

**Why 5/5:** The human brain holds 5 items in working memory without effort. At 6, scanning begins. This limit ensures that at every single point in the codebase, the local view never changes. You open a folder and see 5 things or fewer, always, whether you are at depth 1 or depth 9.

---

## Rule 2 — The 500-Line Ceiling

**No `.py` file contains more than 500 lines.** Blank lines and comments count. Docstrings count. At 501 lines, the file must become a folder.

### How a file becomes a folder

`d3_2_belief_revise.py` at 501 lines becomes the folder `d3_2_belief_revise/`. Inside that folder, you create new files at depth 4, each handling one real sub-concern of the original.

### The Temporary Scaffold

You may leave a 1-line redirect at the old path to keep the codebase running during the refactor. This is the only exception to the no-redirect rule. It must be a single line (e.g., a lambda or a direct assignment), and it counts against the 5-file limit at that level. 

This scaffold has a strict lifespan: it dies the moment the auto-import tool rewrites all importers to point to the new, deeper files, or by the end of the current refactoring session. It is never committed as permanent architecture. A redirect file is a temporary signpost, not a room.

### The only other exception: `__init__.py`

Each folder may contain one `__init__.py`. It must be empty or contain only `# intentionally empty`. It exists to make the folder a Python package. It contains no logic, no imports, no re-exports. Its line count does not factor into the 500-line ceiling.

---

## Rule 3 — The Depth-Sequence Coordinate

**Every file and folder is named with this exact pattern:**

```
{Depth}_{Sequence}_{Word1}_{Word2}
```

- **Depth**: A single digit (1–9) representing how many folders deep this item is from the `serin/` root. `serin/` itself is depth 0. Its direct children are depth 1. Their children are depth 2. And so on. The filename begins with `d` so the coordinate stays valid in Python.
- **Sequence**: A single digit (1–5) representing this item's position among its siblings, ordered by their role in the system's data flow — earliest in the pipeline first, most fundamental first.
- **Word1_Word2**: Exactly two English words separated by an underscore. The first word is a verb or a role noun. The second word is the subject. No abbreviations. No acronyms. No implementation details (not `sqlite_db`, but `memory_store`). No cute names. No single-word names. No three-word names.

**Examples of correct names:**
- `d1_1_pipeline/` — depth 1, first item, pipeline stage
- `d3_2_belief_revise.py` — depth 3, second item, belief revision
- `d4_5_error_base.py` — depth 4, fifth item, base error classes

**Examples of illegal names:**
- `utils.py` — no coordinate, one word, junk drawer
- `d2_1_mgr.py` — abbreviation
- `d3_3_enhanced_message_manager.py` — three words
- `helpers/` — no coordinate, junk drawer
- `d1_2_gateway/` — capitalized

**The coordinate is not decoration.** A person reading `d4_2_belief_revise.py` knows without opening it: this file is 4 levels deep, it is the second concern at that level, it handles belief revision. The name contains the address. You do not need the full path to know where you are.

---

## Rule 4 — The Law of Buoyancy

**The depth of a file is determined by how specific its concern is.** General concerns float toward depth 1. Specific concerns sink toward depth 9. There is no judgment involved — you answer one question:

> "How many branches of the codebase need this?"

- **Multiple top-level branches need it** → it belongs in `serin/state/` at depth 1. Examples: the logger, shared data types, base error classes.
- **One top-level branch needs it** → it belongs inside that branch at depth 2 or deeper. Examples: voice-specific data types belong inside `serin/gateway/voice/`, not in `serin/state/`.
- **One specific stage of one branch needs it** → it sinks to exactly that stage. Examples: BM25 index logic belongs inside `serin/pipeline/remember/`, not at the top of the pipeline.

**The practical test for "does this belong in state/?"**
After you write the file, grep for its imports across the whole codebase. If files from more than one top-level branch import it, it belongs in `state/`. If only files from one top-level branch import it, it belongs inside that branch — not in `state/`. Move it down.

**There is no "I'm not sure" answer.** If you are unsure, run the grep. The grep tells you. You do not decide — the import count decides.

---

## Rule 5 — The Depth DAG (Directed Acyclic Graph)

**A file may only import from files that have a strictly shallower Depth number.** 

Look at the first digit of the target file's coordinate (after the leading `d`). Look at the first digit of the importing file's coordinate (after the leading `d`). The target's digit must be strictly less than the importer's digit. 

If `Target_Depth < Importer_Depth`, the import is **LEGAL**.
If `Target_Depth >= Importer_Depth`, the import is **ILLEGAL**.

This single mathematical rule replaces all complex path-tracking. You do not need to look at the folder structure. You only look at the numbers on the files.

**Concrete examples:**

| Importer | Target | Math | Verdict |
| :--- | :--- | :--- | :--- |
| `d3_2_msg_decode.py` | `d2_1_ingest.py` | $2 < 3$ | **LEGAL** (Child imports parent) |
| `d3_2_msg_decode.py` | `d1_3_state_types.py` | $1 < 3$ | **LEGAL** (Deep node imports root state) |
| `d3_2_msg_decode.py` | `d3_4_msg_route.py` | $3 < 3$ (False) | **ILLEGAL** (Siblings cannot see each other) |
| `d4_1_store.py` | `d2_5_act.py` | $2 < 4$ | **LEGAL** (Deep node imports distant ancestor) |
| `d1_1_pipeline.py` | `d1_4_config.py` | $1 < 1$ (False) | **ILLEGAL** (Top-level branches are blind to each other) |

**How top-level branches share dependencies:**
Because depth-1 folders cannot import from other depth-1 folders (`1 < 1` is false), they do not share code by importing each other. They share code through **Dependency Injection from the Root**. The `discord_bot.py` entry point imports `serin/state/` and `serin/config/`, instantiates them, and passes those instances down into `serin/pipeline/` and `serin/gateway/` during startup. The branches never import each other. The root is the composer.

**What to do when you discover an illegal import:**
Do not change the import path to make it work. Ask: should the imported thing be in `state/` so deeper nodes can reach it? If yes, move it to `state/`. If only one branch needs it, it sinks into that branch. There is no third option.

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
# (the primary public functions or classes this file exposes — the "front door")

# --- Core ---
# (the main logic: functions and methods called by Entry)

# --- Helpers ---
# (private functions called only by Core, prefixed with _)

# --- Errors ---
# (exception classes defined in this file, if any)
```

Every section header must be present in every file, even if the section is empty. An empty section looks like:
```python
# --- Types ---
# (none)
```

**Why every section must exist:** A person who has read three files in this codebase knows where to look for error handling in the fourth without scrolling. The section is always there. It is always in that position. If the section is empty, the person confirms it in one second and moves on. The empty section costs nothing. The missing section costs trust.

**The one primary concern rule:** Every file handles exactly one primary concern — the thing in the `# --- Entry ---` section. A file defining three different exception classes for the belief system is doing one job (handling belief errors). A file defining a database connector, an HTTP client, and a logger is doing three jobs and must be split.

---

## Rule 7 — No Junk Drawers

**These folder names are permanently banned:** `utils/`, `helpers/`, `common/`, `misc/`, `shared/`, `tools/`, `lib/`, `core/` (when used as a catch-all).

A junk drawer is any folder whose contents cannot be described in one sentence that doesn't use the word "various," "miscellaneous," "shared," or "common." If you cannot say exactly what a folder contains without those words, the folder is a junk drawer.

**What to do instead of creating a junk drawer:**
For each file you would have put in `utils/`, ask: which top-level branch actually uses this? If one branch uses it, it sinks into that branch. If multiple branches use it, it belongs in `serin/state/`. Run the import grep. The answer is always one of those two options.

The ban on `core/` as a catch-all is specific: `core/` is legal as a subfolder name if it means "the core logic of this specific parent folder" — e.g., `serin/pipeline/remember/core/` containing the main store logic for the remember stage. It is illegal as a depth-1 folder named `serin/core/` that contains "foundational stuff" — that is `serin/state/`.

---

## The Top-Level Structure (Fixed, Not Negotiable)

`serin/` contains exactly these five items:

```
serin/
├── pipeline/    # The message lifecycle: ingest → perceive → think → remember → act
├── gateway/     # I/O boundaries: Discord, voice, text, media, model adapters
├── state/       # General truths injected by root: types, logger, constants
├── config/      # Environment variables, secrets, bot settings (loaded by root, passed down)
└── ops/         # Operational machinery: deployment, law checkers, hot reload, backup
```

These five names are fixed. They do not change. A new top-level concern does not get a sixth folder — it fits into one of these five or it does not exist yet. If you genuinely cannot fit a new top-level concern into any of these five, you stop and discuss it before creating anything. You do not create a sixth folder unilaterally.

**What lives where, resolved once:**

| Concept | Location | Why |
|---|---|---|
| Logger | `serin/state/` | Passed down by root to Pipeline and Ops |
| Base exception class | `serin/state/` | Passed down by root to Pipeline |
| Shared dataclasses (MessageContext, etc.) | `serin/state/` | Pipeline uses them to wrap raw dicts from Gateway |
| DatabaseProtector | `serin/state/` | Passed down by root to Pipeline and Ops |
| Discord client setup | `serin/gateway/discord/` | Only the gateway owns the Discord connection |
| Voice bridge (Rust) | `serin/gateway/voice/` | Only the gateway owns the voice connection |
| LLM model connectors | `serin/gateway/model/` | Only the gateway owns the model connection |
| Qdrant memory store | `serin/pipeline/remember/` | Only the remember stage writes/reads memories |
| Belief state machine | `serin/pipeline/act/believe/` | Only the act stage manages beliefs |
| Evidence store | `serin/pipeline/remember/` | Evidence is memory, not an action |
| Hot reloader | `serin/ops/` | Operational tooling, not domain logic |
| Database backup | `serin/ops/` | Operational tooling, not domain logic |
| Law check scripts | `scripts/` | Not source code, not tests — automation |

If a concept is not in this table, apply Rule 4 (run the import grep, let the count decide) and add it to this table before committing.

---

## Verification

These checks run on every commit via `.git/hooks/pre-commit`. A commit that fails any check is rejected. There are no warnings, only pass or fail.

```bash
#!/usr/bin/env bash
set -e
python3 scripts/law/check_structure.py   # Rules 1, 2, 3
python3 scripts/law/check_imports.py     # Rule 5
DISCORD_TOKEN=test pytest tests/ --ignore=tests/test_vision.py -m "not integration" -q
```

`check_structure.py` fails if:
- Any directory contains more than 5 subdirectories OR more than 5 files.
- Any `.py` file (outside `tests/`) exceeds 500 lines.
- Any file or folder name does not match `{digit}_{digit}_{word}_{word}.py` or the exact root exceptions (`discord_bot.py`, `hot_reloader.py`, `pyproject.toml`, `README.md`, `__init__.py`, `conftest.py`).

`check_imports.py` fails if:
- Any import targets a file whose Depth number is greater than or equal to the importer's Depth number (The Depth DAG rule).
- Any file in `serin/gateway/` imports anything from `serin/state/` or `serin/pipeline/` directly, instead of receiving it via function arguments from the root.
- Any file in `serin/ops/` is imported by any file in `serin/pipeline/` or `serin/gateway/`.

These are not suggestions. A green pre-commit hook is the definition of "this follows the Law." A commit message that says "follows the Law" without a green hook is not evidence of anything.
