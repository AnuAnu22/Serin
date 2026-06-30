# Serin: The Architecture Law

This is not a style guide. This is the physical structure of the codebase.
The location of a line of code is not decided by a developer — it is
determined by these rules. A beginner with two days of Python experience
should be able to find any line in this codebase by looking, not by
grepping, asking, or reasoning about categories.

## Rule 1 — The 5/5 Horizon
No directory contains more than 5 subdirectories or more than 5 files.
If a 6th item is needed, the existing items are wrong — reorganize, don't
add an exception.

## Rule 2 — The 500-Line Ceiling
No file exceeds 500 lines. At 501 lines, the file becomes a folder
(Rule 2a). There are no exceptions for "this file is just inherently
complex" — complexity is handled by depth, not by length.

### Rule 2a — How a file becomes a folder
`x-y_name.py` at 501 lines becomes a folder `x-y_name/` containing up to
5 new files at the next depth, each handling one real sub-concern of the
original file. This can recurse — a sub-file that itself grows past 500
lines becomes a folder the same way. Depth absorbs complexity; length never
does.

### Rule 2b — The redirect lifecycle
When a file becomes a folder mid-migration, a temporary single-line
redirect may exist at the old import path during the transition. It is
scaffolding, not architecture. It must be deleted and all importers
repointed to the real location within the same migration session — it
never survives as a permanent resident, and it never counts as a real
occupant of its directory's 5/5 budget once the migration session ends.

## Rule 3 — The Depth-Sequence Coordinate
Every file and folder is named `{Depth}-{Sequence}_{word1-word2}`:
- Depth: single digit, how deep from root
- Sequence: single digit 1-5, position among siblings
- Name: exactly two words, a verb or role, no abbreviations
- Example: `4-2_belief-revise.py`

## Rule 4 — The Law of Buoyancy
Specificity determines depth. General truths the whole system relies on
float to the top (`1-3_state/`, `1-4_config/`). Specific implementations
sink to where they're used. If a concept doesn't fit its current parent
without straining the 5/5 limit, it's misplaced — move it, don't force it.
A concept that is genuinely shared across multiple pipeline stages belongs
at the depth where it's a common ancestor of everything that needs it —
never duplicated into multiple branches.

## Rule 5 — The Up-and-Left Boundary
A file may import from its ancestors (the full chain to root) and from the
siblings of its ancestors. It may never import from a cousin — a child of
a different branch at the same or similar depth. Depth-1 folders
(`1-3_state/`, `1-4_config/`) are ancestors of everything below them and
are always reachable via the up-chain from any depth — this is not an
exception, it's what "ancestor" means when the folder is the root's direct
child. What is illegal: going up past one branch and back down into a
different branch's children (a true cousin import).

## Rule 6 — Internal File Anatomy
Every Python file follows this section order, always, even in short files:
```python
"""One sentence. What this does."""
# --- Imports ---
# --- Types ---
# --- Constants ---
# --- Entry ---
# --- Core ---
# --- Helpers ---
# --- Errors ---
```
A beginner who has read three files in this codebase knows where the error
handling is in the fourth, without scrolling to check.

## Rule 7 — No Junk Drawers
There is no `utils/`, `misc/`, `helpers/`, or `common/` folder. Every file
declares what it does by where it lives. If something feels like "utils,"
that's a sign it's either general enough to float to `1-3_state/`, or
specific enough to sink into the stage that actually uses it. There is
always a real answer — "utils" is what happens when nobody looked for it.

## Verification, not trust
Every claim that "this follows the Law" must be checked by the scripts in
`scripts/law/` (Phase 6), not asserted in a commit message. A directory
that violates Rule 1 or Rule 2 fails the build.
