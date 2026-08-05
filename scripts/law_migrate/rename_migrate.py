#!/usr/bin/env python3
"""Plan (and, on request, execute) in-place renames to bring every file and
folder under serin/ into THE_LAW's dN_seq_word_word coordinate format,
then rewrite every import site across the codebase to match.

Deliberately NARROW in scope, matching what was actually asked for:
- Files and folders are renamed IN PLACE. Nothing moves to a different
  directory. A file at serin/x/y/z.py becomes serin/x/y/d{N}_{s}_a_b.py —
  same folder, new name. This is the "grueling by hand, mechanical by
  tool" problem: 138 renames × every import site across ~150 files.
- This does NOT decide where a file *should* live (Rule 4, the Law of
  Buoyancy) — that's an architectural judgment call, not a renaming
  problem, and folding it in here would risk silently restructuring the
  codebase's actual behavior, not just its file names.
- This does NOT choose semantically perfect Word1/Word2 pairs. Rule 3
  asks for "a verb or role noun" + "the subject", in true data-flow
  order — that requires understanding what each file *does*, which is a
  judgment call a mechanical tool can't make safely. What this DOES do:
  derive a defensible, deterministic name from the file's existing stem
  and its parent folder, and flag every name it generates as a
  first-draft suggestion, not a verified-correct one. A human should
  skim generated_plan.json before applying it — see PLAN_ONLY mode.

Usage:
    python3 scripts/law_migrate/rename_migrate.py plan
        Writes migration_plan.json — every proposed rename, no changes
        made to any file yet. Safe to run any time; makes no edits.

    python3 scripts/law_migrate/rename_migrate.py apply [--plan FILE]
        Executes the plan: git-mv's every renamed file/folder, rewrites
        every import site across the whole repo to match, then re-runs
        THE LAW's own checkers as a self-check. Refuses to run if the
        working tree has uncommitted changes outside what the plan itself
        will touch, so a bad run can always be cleanly reverted with
        `git checkout -- .` or `git reset --hard`.

    python3 scripts/law_migrate/rename_migrate.py apply --dry-run
        Same as apply, but prints every file it WOULD change without
        writing anything — the way to sanity-check the import-rewrite
        logic before trusting it with `git mv`.
"""

# --- Imports ---
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field


# --- Types ---
@dataclass
class RenameEntry:
    """One proposed rename: a single file or folder, staying in the same
    parent directory, getting a new dN_seq_word_word name."""
    old_path: str          # relative to repo root, e.g. "serin/x/y/store.py"
    new_path: str          # relative to repo root, e.g. "serin/x/y/d4_1_data_store.py"
    old_module: str        # dotted module path, e.g. "serin.x.y.store"
    new_module: str        # dotted module path, e.g. "serin.x.y.d4_1_data_store"
    kind: str              # "file" or "folder"
    depth: int
    sequence: int
    confidence: str        # "high" (already had 2+ words) or "low" (single-word, parent-name fallback used)


@dataclass
class MigrationPlan:
    entries: list[RenameEntry] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps([asdict(e) for e in self.entries], indent=2)

    @staticmethod
    def from_json(text: str) -> MigrationPlan:
        raw = json.loads(text)
        return MigrationPlan(entries=[RenameEntry(**e) for e in raw])


# --- Constants ---
PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SERIN = os.path.join(PROJECT, "serin")
IGNORED_DIR_NAMES = {"__pycache__", "logs", ".pytest_cache"}
EXEMPT_FILENAMES = {"__init__.py", "conftest.py", "__main__.py"}
# Python-magic filenames are never renamed regardless of how many words
# they contain. __main__.py in particular is looked up by the Python
# runtime itself (`python -m serin`) by exact filename — nothing "imports"
# it in the sense this tool can rewrite, so renaming it would silently
# break the entry point with no error at rename time, only at next launch.
COORDINATE_RE = re.compile(r"^d[1-9]_[1-5]_[a-z]+_[a-z]+$")
DEFAULT_PLAN_PATH = os.path.join(PROJECT, "scripts", "law_migrate", "migration_plan.json")


# --- Entry ---
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    plan_cmd = sub.add_parser("plan", help="Compute the rename plan, write it to disk, make no edits.")
    plan_cmd.add_argument("--out", default=DEFAULT_PLAN_PATH)

    apply_cmd = sub.add_parser("apply", help="Execute a previously generated plan.")
    apply_cmd.add_argument("--plan", default=DEFAULT_PLAN_PATH)
    apply_cmd.add_argument("--dry-run", action="store_true", help="Print what would change, write nothing.")
    apply_cmd.add_argument("--skip-verify", action="store_true", help="Skip running THE LAW checkers afterward.")

    args = parser.parse_args()

    if args.command == "plan":
        return cmd_plan(args.out)
    if args.command == "apply":
        return cmd_apply(args.plan, dry_run=args.dry_run, skip_verify=args.skip_verify)
    return 1


# --- Core ---
def cmd_plan(out_path: str) -> int:
    plan = build_plan()
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(plan.to_json())
    print(f"Planned {len(plan.entries)} renames -> {out_path}")
    low = [e for e in plan.entries if e.confidence == "low"]
    if low:
        print(
            f"\n{len(low)} of these used the parent-folder-name fallback "
            f"(the original name was a single word, e.g. 'store.py' -> "
            f"'d4_1_core_store.py' using the parent folder 'core/' as "
            f"Word1). These are first-draft names — skim them in "
            f"{out_path} before running 'apply'. Rule 3 asks for a "
            f"verb/role-noun + subject pair in true data-flow order; this "
            f"tool can only give you a deterministic, defensible guess, "
            f"not a semantically verified one."
        )
    return 0


def cmd_apply(plan_path: str, dry_run: bool, skip_verify: bool) -> int:
    if not os.path.isfile(plan_path):
        print(f"No plan at {plan_path} — run 'plan' first.", file=sys.stderr)
        return 1

    with open(plan_path, encoding="utf-8") as f:
        plan = MigrationPlan.from_json(f.read())

    if not dry_run and not _working_tree_is_clean_enough():
        print(
            "Working tree has uncommitted changes. Commit or stash them "
            "first — this tool needs a clean base so a bad run can be "
            "reverted with a single 'git reset --hard' if anything goes "
            "wrong. Use --dry-run to preview without this requirement.",
            file=sys.stderr,
        )
        return 1

    rename_map = {e.old_module: e.new_module for e in plan.entries}
    segment_map = _build_segment_map(plan)

    print(f"{'[DRY RUN] ' if dry_run else ''}Rewriting imports across the repo...")
    changed_files = rewrite_all_imports(rename_map, segment_map, dry_run=dry_run)
    print(f"  {len(changed_files)} file(s) had import statements rewritten.")

    print(f"{'[DRY RUN] ' if dry_run else ''}Renaming {len(plan.entries)} file(s)/folder(s)...")
    # Stage-then-swap, not incremental git mv. Every incremental approach
    # (translate-as-you-go, sort-by-various-depths, separate source/target
    # resolution) kept running into the same root cause: `mv src dst`
    # nests src INSIDE dst instead of renaming, the instant dst already
    # exists as a directory — and during a multi-level rename, dst's
    # parent almost always already exists by the time a deeper entry
    # executes, because a shallower sibling or the folder's own
    # not-yet-processed rename left it there. No amount of reordering
    # fully escapes this while still using `mv` as the primitive.
    #
    # Building the complete final tree fresh in an empty staging
    # directory sidesteps the whole problem: nothing in staging/ ever
    # pre-exists when a file is copied into it, because staging/ starts
    # genuinely empty and every path within it is used exactly once.
    # Once staging/ is a complete, correct mirror of the final tree,
    # serin/ is deleted and staging/ is renamed to serin/ in one atomic
    # swap — a single top-level move with no nested-nesting possible,
    # since serin/ no longer exists at the moment the swap happens.
    _stage_and_swap(plan.entries, dry_run=dry_run)

    if dry_run:
        print("\n[DRY RUN] No files were actually changed.")
        return 0

    if skip_verify:
        return 0

    print("\nVerifying with THE LAW's own checkers...")
    return _run_verification()


# --- Helpers ---
def build_plan() -> MigrationPlan:
    entries: list[RenameEntry] = []
    for root, dirs, files in os.walk(SERIN):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIR_NAMES)
        rel_root = os.path.relpath(root, PROJECT)
        depth = len(rel_root.split(os.sep))  # children of serin/ are depth 1

        non_compliant_dirs = sorted(d for d in dirs if not COORDINATE_RE.match(d))
        for seq, name in enumerate(non_compliant_dirs, start=1):
            old_path = os.path.join(rel_root, name)
            word1, word2, confidence = _derive_words(name, parent_hint=os.path.basename(rel_root))
            new_name = f"d{depth}_{min(seq, 5)}_{word1}_{word2}"
            new_path = os.path.join(rel_root, new_name)
            entries.append(RenameEntry(
                old_path=old_path, new_path=new_path,
                old_module=_path_to_module(old_path), new_module=_path_to_module(new_path),
                kind="folder", depth=depth, sequence=min(seq, 5), confidence=confidence,
            ))

        py_files = sorted(f for f in files if f.endswith(".py") and f not in EXEMPT_FILENAMES)
        non_compliant_files = [f for f in py_files if not COORDINATE_RE.match(f[:-3])]
        # Sequence continues after directories at this level, matching
        # "position among siblings" — files and folders share one
        # sequence space in the same parent per Rule 3's own examples
        # (d1_1_pipeline/ sits alongside d1_2_*.py-style siblings).
        start_seq = len(non_compliant_dirs) + 1
        for offset, name in enumerate(non_compliant_files):
            seq = start_seq + offset
            stem = name[:-3]
            old_path = os.path.join(rel_root, name)
            word1, word2, confidence = _derive_words(stem, parent_hint=os.path.basename(rel_root))
            new_name = f"d{depth}_{min(seq, 5)}_{word1}_{word2}.py"
            new_path = os.path.join(rel_root, new_name)
            entries.append(RenameEntry(
                old_path=old_path, new_path=new_path,
                old_module=_path_to_module(old_path), new_module=_path_to_module(new_path),
                kind="file", depth=depth, sequence=min(seq, 5), confidence=confidence,
            ))

    return MigrationPlan(entries=entries)


def _derive_words(name: str, parent_hint: str) -> tuple[str, str, str]:
    """Derive (word1, word2, confidence) for a name that needs a coordinate.

    High confidence: the existing name already has two or more
    underscore-separated words — take the last two as-is (closest to
    Rule 3's "verb/role noun + subject" shape without inventing anything).

    Low confidence: the existing name is a single word. Pair it with the
    immediate parent folder's own (already-cleaned) name as word1, since
    that's the most concrete, truthful context available without reading
    and understanding the file's actual logic. E.g. 'store.py' inside
    'core/' becomes word1='core', word2='store' — not perfect Rule-3
    grammar, but truthful and stable, and clearly flagged for human
    review via the 'confidence' field.
    """
    clean = re.sub(r"^d\d+_\d+_", "", name.lower())
    parts = [p for p in clean.split("_") if p]

    if len(parts) >= 2:
        return parts[-2], parts[-1], "high"

    single = parts[0] if parts else "item"
    parent_clean = re.sub(r"^d\d+_\d+_", "", parent_hint.lower())
    parent_parts = [p for p in parent_clean.split("_") if p]
    parent_word = parent_parts[-1] if parent_parts else "module"

    if parent_word == single:
        # Parent folder and file share the exact same word (e.g.
        # remember/remember.py, which shouldn't happen but might) —
        # fall back to a neutral second word rather than doubling up.
        return single, "core", "low"

    return parent_word, single, "low"


def _path_to_module(rel_path: str) -> str:
    without_ext = rel_path[:-3] if rel_path.endswith(".py") else rel_path
    return without_ext.replace(os.sep, ".")


def _build_segment_map(plan: MigrationPlan) -> dict[str, dict[str, str]]:
    """Build a per-parent segment rename map: {old_parent_module: {old_segment: new_segment}}.

    Whole-module matching alone (rename_map) only catches an import whose
    ENTIRE dotted path exactly equals something renamed. It misses the far
    more common case where an import passes THROUGH a renamed ancestor —
    e.g. `serin.d1_5_ops_tooling.control_panel.server` where both
    `control_panel` and `server` got renamed independently in the same
    pass. A whole-string map has no way to compose those two edits.

    Scoping each segment's rename by its exact parent path (rather than a
    single global old-name -> new-name map) matters because the same bare
    word could appear as a folder name under two different parents with
    two different new names — using the parent as the scope key keeps
    those cases from colliding.
    """
    segment_map: dict[str, dict[str, str]] = {}
    for e in plan.entries:
        parent_module = ".".join(e.old_module.split(".")[:-1])
        old_segment = e.old_module.split(".")[-1]
        new_segment = e.new_module.split(".")[-1]
        segment_map.setdefault(parent_module, {})[old_segment] = new_segment
    return segment_map


def _resolve_renamed_module(module: str, segment_map: dict[str, dict[str, str]]) -> str | None:
    """Given a dotted module path, return its fully-renamed form if any
    segment along the path needs rewriting, else None if nothing changed.

    Walks every segment left to right and rewrites it using segment_map,
    scoped to the (already-rewritten) parent path built so far — so a path
    where BOTH an ancestor and the leaf were renamed gets both
    substitutions composed correctly, in order.

    Deliberately does NOT shortcut via a whole-path rename_map lookup: an
    exact match there (e.g. "serin.x.control_panel.server" ->
    "serin.x.control_panel.d3_2_panel_server") only encodes the rename of
    that entry's OWN segment — it says nothing about whether an ANCESTOR
    segment earlier in the same path (like "control_panel" itself) was
    also renamed in this same pass. Trusting it as fully-resolved was the
    original bug: it silently left every renamed ancestor's old name
    sitting inside otherwise-correct-looking output. Walking segment_map
    for every part, unconditionally, is the only way to catch both.
    """
    parts = module.split(".")
    changed = False
    new_parts: list[str] = []
    built_old_prefix = ""
    for part in parts:
        replacement = segment_map.get(built_old_prefix, {}).get(part)
        if replacement is not None:
            new_parts.append(replacement)
            changed = True
        else:
            new_parts.append(part)
        built_old_prefix = f"{built_old_prefix}.{part}" if built_old_prefix else part

    return ".".join(new_parts) if changed else None


def rewrite_all_imports(rename_map: dict[str, str], segment_map: dict[str, dict[str, str]], dry_run: bool) -> list[str]:
    """Rewrite every `import X` / `from X import Y` across the whole repo
    (serin/, tests/, scripts/, and the two root entry files) where X is a
    key in rename_map, to use the new module path instead. Uses precise
    AST-node offsets so only the module path itself is rewritten — the
    rest of the line (imported names, aliases, comments) is untouched."""
    changed: list[str] = []
    search_roots = [SERIN, os.path.join(PROJECT, "tests"), os.path.join(PROJECT, "scripts")]
    all_files = []
    for base in search_roots:
        if os.path.isdir(base):
            for root, dirs, files in os.walk(base):
                dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIR_NAMES)
                for f in sorted(files):
                    if f.endswith(".py"):
                        all_files.append(os.path.join(root, f))
    for extra in ("discord_bot.py", "hot_reloader.py"):
        p = os.path.join(PROJECT, extra)
        if os.path.isfile(p):
            all_files.append(p)

    for fp in sorted(all_files):
        new_text = _rewrite_file_imports(fp, rename_map, segment_map)
        if new_text is not None:
            changed.append(os.path.relpath(fp, PROJECT))
            if not dry_run:
                with open(fp, "w", encoding="utf-8") as f:
                    f.write(new_text)

    return changed


def _rewrite_file_imports(fp: str, rename_map: dict[str, str], segment_map: dict[str, dict[str, str]]) -> str | None:
    """Return the file's new text if any import needed rewriting, else
    None. Rewrites `import a.b.c`, `from a.b.c import X`, and relative
    (`from .x import Y`, `from ..x.y import Z`) forms via exact AST-node
    offsets, so only the module path substring itself is touched —
    imported names, aliases, comments, and surrounding formatting are
    left exactly as they were. Handles both single-line and parenthesized
    multi-line import statements, and composes multiple renamed segments
    within a single import path (see _resolve_renamed_module)."""
    try:
        with open(fp, encoding="utf-8") as f:
            original = f.read()
    except (OSError, UnicodeDecodeError):
        return None

    try:
        tree = ast.parse(original, filename=fp)
    except SyntaxError:
        return None  # can't safely rewrite a file that doesn't parse

    lines = original.splitlines(keepends=True)
    line_offsets = _line_start_offsets(lines)
    file_package = _containing_package_module(fp)

    edits: list[tuple[int, int, str]] = []  # (abs_start, abs_end, replacement)
    visited_attribute_ids: set[int] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # Relative import: `from .controls import X` or
                # `from ..pkg.mod import Y`. node.module holds only the
                # part after the dots (e.g. "controls", or "pkg.mod"),
                # which can't be resolved on its own — "controls" alone
                # was never a key in any rename map. Reconstruct the
                # absolute module path using this FILE's own package
                # location (one ".." per level beyond 1), resolve THAT,
                # then rewrite only the trailing dotted part after the
                # dots — the dots themselves never change, since the
                # file's relative position to its own package doesn't
                # move just because a sibling got renamed.
                absolute = _relative_to_absolute(file_package, node.level, node.module)
                new_absolute = _resolve_renamed_module(absolute, segment_map)
                if new_absolute is not None and node.module:
                    # Strip the same number of leading segments we added,
                    # to get back just the "after the dots" part in its
                    # new form.
                    old_trailing_len = len((node.module or "").split("."))
                    new_trailing = ".".join(new_absolute.split(".")[-old_trailing_len:])
                    if node.module:
                        span = _find_module_span_in_from_import(original, line_offsets, node)
                        if span is not None:
                            abs_start, abs_end = span
                            edits.append((abs_start, abs_end, new_trailing))
                continue
            if node.module:
                new_module = _resolve_renamed_module(node.module, segment_map)
                if new_module is not None:
                    span = _find_module_span_in_from_import(original, line_offsets, node)
                    if span is not None:
                        abs_start, abs_end = span
                        edits.append((abs_start, abs_end, new_module))

                # Separately: the IMPORTED NAME itself can be a renamed
                # submodule, not just the base module path — e.g.
                # `from serin.x.y import bot_pipeline_init` where
                # bot_pipeline_init is a folder that got renamed to
                # d3_1_pipeline_init. This is `from package import
                # submodule` syntax; Python resolves it by importing
                # package.submodule as a side effect, so the "name" being
                # imported IS a module path segment, just spelled as a
                # bare name instead of part of the dotted `module` string.
                # Missing this left every such import silently pointing
                # at a name that no longer exists once the submodule was
                # renamed — a real ImportError at runtime, not just a
                # style nit.
                for alias in node.names:
                    candidate = f"{node.module}.{alias.name}"
                    new_candidate = _resolve_renamed_module(candidate, segment_map)
                    if new_candidate is not None:
                        new_name = new_candidate.split(".")[-1]
                        if new_name != alias.name:
                            # Rewrite the imported name itself — required
                            # even when the import uses `as` (e.g. `from X
                            # import bot_pipeline_init as bp`): the alias
                            # only renames the LOCAL binding used after
                            # the import; Python still has to find
                            # X.bot_pipeline_init to resolve the import at
                            # all, so if that submodule was renamed, this
                            # name must change too.
                            #
                            # IMPORTANT: when asname is present,
                            # alias.col_offset/end_col_offset span the
                            # WHOLE "original as alias" phrase, not just
                            # "original" — confirmed directly against
                            # ast's own output. Must compute just the
                            # bare-name portion's span, or this would
                            # delete the alias entirely (turning `import
                            # bot_pipeline_init as bp` into `import
                            # d3_1_pipeline_init`, silently breaking every
                            # `bp.` reference later in the file).
                            abs_start = _to_absolute(line_offsets, alias.lineno, alias.col_offset)
                            if alias.asname:
                                abs_end = abs_start + len(alias.name)
                            else:
                                abs_end = _to_absolute(line_offsets, alias.end_lineno, alias.end_col_offset)
                            edits.append((abs_start, abs_end, new_name))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                new_module = _resolve_renamed_module(alias.name, segment_map)
                if new_module is not None:
                    # IMPORTANT: for `import X as Y`, alias.col_offset /
                    # end_col_offset span the WHOLE "X as Y" phrase, not
                    # just X — confirmed directly against ast's own
                    # output. Using the full span without accounting for
                    # `as` silently deletes the alias entirely: `import
                    # serin.x.discord.bot as bot_module` becomes `import
                    # serin.x.d3_2_discord_bot`, losing `bot_module`
                    # completely and breaking every one of its uses
                    # elsewhere in the file. Compute just the
                    # module-name portion's span when an alias is present.
                    abs_start = _to_absolute(line_offsets, alias.lineno, alias.col_offset)
                    if alias.asname:
                        abs_end = abs_start + len(alias.name)
                    else:
                        abs_end = _to_absolute(line_offsets, alias.end_lineno, alias.end_col_offset)
                    edits.append((abs_start, abs_end, new_module))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            # String literals that happen to spell a serin.* module path —
            # overwhelmingly unittest.mock.patch("serin.x.y.Z") targets,
            # also importlib.import_module("serin.x.y") calls. These are
            # real references to a module, but they're invisible to
            # ast.Import/ast.ImportFrom since they're just strings from
            # the parser's point of view — a plain import-statement
            # rewriter has no reason to ever look at a Constant node.
            # Skipped, this class of test-mock reference goes stale
            # silently: the test file still parses and imports fine, it
            # just patches a path that no longer exists, so the mock
            # never actually intercepts anything — a failure mode much
            # harder to notice than an ImportError.
            text = node.value
            if text.startswith("serin.") and _looks_like_dotted_module_path(text):
                new_text = _resolve_renamed_module(text, segment_map)
                if new_text is not None:
                    abs_start = _to_absolute(line_offsets, node.lineno, node.col_offset)
                    abs_end = _to_absolute(line_offsets, node.end_lineno, node.end_col_offset)
                    # +1/-1 to land inside the quote characters, since the
                    # Constant node's span includes the quotes themselves.
                    edits.append((abs_start + 1, abs_end - 1, new_text))
        elif isinstance(node, ast.Attribute) and id(node) not in visited_attribute_ids:
            # Bare dotted attribute-access chains OUTSIDE any import
            # statement — e.g. `serin.d1_1_pipeline_flow.think.
            # response_generator.discord_client = client`. This happens
            # when a module was imported with plain `import serin.x.y.z`
            # (no `from`, no `as`) and then referenced later via its full
            # dotted path rather than a short local name. Found by
            # diffing mypy's error output against the pre-migration
            # codebase — these are invisible to ast.Import/ImportFrom
            # entirely, since they're not import statements at all, just
            # ordinary attribute-access expressions that happen to spell
            # out a module path.
            #
            # `visited_attribute_ids` prevents reprocessing the same
            # chain from an inner node — ast.walk visits every Attribute
            # node in a chain, not just the outermost one, and only the
            # outermost one's full text should be resolved.
            chain_root, chain_text = _flatten_attribute_chain(node)
            for inner in ast.walk(node):
                visited_attribute_ids.add(id(inner))
            if chain_root == "serin" and _looks_like_dotted_module_path(chain_text):
                # Try progressively shorter prefixes of the chain (the
                # trailing segment(s) are very likely a real attribute
                # like .discord_client, not part of the module path) —
                # take the LONGEST prefix that actually resolves to a
                # rename, since a shorter prefix could coincidentally
                # also "resolve" (to itself, unchanged) and we want the
                # most specific match.
                segments = chain_text.split(".")
                for prefix_len in range(len(segments), 1, -1):
                    prefix = ".".join(segments[:prefix_len])
                    new_prefix = _resolve_renamed_module(prefix, segment_map)
                    if new_prefix is not None:
                        suffix = ".".join(segments[prefix_len:])
                        new_text = f"{new_prefix}.{suffix}" if suffix else new_prefix
                        abs_start = _to_absolute(line_offsets, node.lineno, node.col_offset)
                        abs_end = _to_absolute(line_offsets, node.end_lineno, node.end_col_offset)
                        edits.append((abs_start, abs_end, new_text))
                        break

    if not edits:
        return None

    edits.sort(key=lambda e: e[0], reverse=True)
    new_text = original
    for start, end, replacement in edits:
        new_text = new_text[:start] + replacement + new_text[end:]
    return new_text


def _containing_package_module(fp: str) -> str:
    """Return the dotted module path of the PACKAGE containing file fp
    (i.e. its own directory, as a module path) — the base a relative
    import is resolved against. E.g. for
    serin/d1_5_ops_tooling/control_panel/server/__init__.py, returns
    "serin.d1_5_ops_tooling.control_panel.server". For a non-__init__.py
    file, Python resolves relative imports against the file's OWN
    package (its directory), same as for __init__.py — the file itself
    is not part of the package path used for `.` resolution.
    """
    rel = os.path.relpath(fp, PROJECT)
    directory = os.path.dirname(rel)
    return directory.replace(os.sep, ".")


def _relative_to_absolute(file_package: str, level: int, module: str | None) -> str:
    """Reconstruct the absolute module path a relative import refers to.

    `from . import x` (level=1, module=None) refers to file_package
    itself. `from .controls import x` (level=1, module="controls") refers
    to file_package + ".controls". `from ..other import x` (level=2)
    strips one more segment off file_package first, then appends module.
    """
    parts = file_package.split(".") if file_package else []
    # level=1 means "this package" (no segments stripped); each
    # additional level strips one more trailing segment.
    strip_count = level - 1
    base_parts = parts[: len(parts) - strip_count] if strip_count > 0 else parts
    base = ".".join(base_parts)
    if module:
        return f"{base}.{module}" if base else module
    return base


def _flatten_attribute_chain(node: ast.Attribute) -> tuple[str, str]:
    """Flatten a nested ast.Attribute chain (e.g. serin.x.y.z.attr) into
    (root_name, full_dotted_text). Returns ("", "") if the chain doesn't
    bottom out at a plain ast.Name (e.g. it's actually `(a + b).attr`,
    which isn't a module-path reference at all)."""
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return "", ""
    parts.append(current.id)
    parts.reverse()
    return parts[0], ".".join(parts)


def _looks_like_dotted_module_path(text: str) -> bool:
    """True only for strings that are plausibly a real dotted module path
    — not just any string starting with "serin.". Guards against
    rewriting something like a log message or docstring fragment that
    happens to start the same way.

    Every segment except possibly the LAST must be lowercase
    letters/digits/underscores only (a real module/package name segment).
    The last segment is allowed to be a capitalized identifier too — the
    extremely common `mock.patch("serin.x.y.ClassName")` shape, where the
    trailing segment names a class or attribute being patched, not a
    module. Also rejects strings with spaces or unreasonable length/depth,
    which rules out ordinary prose that happens to contain a period.
    """
    if " " in text or len(text) > 200:
        return False
    segments = text.split(".")
    if len(segments) < 2 or len(segments) > 10:
        return False
    module_segments, last = segments[:-1], segments[-1]
    if not all(re.fullmatch(r"[a-z0-9_]+", seg) for seg in module_segments):
        return False
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", last))


def _find_module_span_in_from_import(
    source: str, line_offsets: list[int], node: ast.ImportFrom,
) -> tuple[int, int] | None:
    """Locate the exact (start, end) absolute offsets of the module name
    within a `from <module> import ...` statement.

    ast.ImportFrom doesn't expose the module substring's own span (only
    the whole statement's), so this searches for it — safely, because we
    only search within the statement's own source range, and we already
    know via node.module exactly which string we're looking for. Handles
    relative imports (node.level > 0) by skipping the leading dots first.
    """
    stmt_start = _to_absolute(line_offsets, node.lineno, node.col_offset)
    stmt_end = _to_absolute(line_offsets, node.end_lineno, node.end_col_offset)
    stmt_text = source[stmt_start:stmt_end]

    # Skip "from" + whitespace + any leading relative-import dots.
    m = re.match(r"from\s+(\.*)", stmt_text)
    if m is None:
        return None
    search_from = m.end()

    module_escaped = re.escape(node.module)
    found = re.search(module_escaped, stmt_text[search_from:])
    if found is None:
        return None

    local_start = search_from + found.start()
    local_end = search_from + found.end()
    return stmt_start + local_start, stmt_start + local_end


def _to_absolute(line_offsets: list[int], lineno: int, col_offset: int) -> int:
    return line_offsets[lineno - 1] + col_offset


def _line_start_offsets(lines: list[str]) -> list[int]:
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    return offsets


def _stage_and_swap(entries: list[RenameEntry], dry_run: bool) -> None:
    """Build the complete post-rename serin/ tree in a staging directory,
    then atomically swap it in.

    Walks the REAL, CURRENT filesystem under serin/ (not just the plan's
    entries) so every file — including ones with no rename entry at all,
    like __init__.py — gets carried into staging automatically, at
    exactly the same relative position, with no special-casing needed.
    Only files whose resolved path actually changes get written to a new
    location; everything else lands at the same relative path it already
    had, which is exactly correct since resolution is a no-op for names
    that were already compliant.
    """
    segment_map = _build_segment_map(MigrationPlan(entries=entries))
    staging = os.path.join(PROJECT, "_law_migrate_staging")

    if os.path.exists(staging):
        shutil.rmtree(staging)

    file_count = 0
    for root, dirs, files in os.walk(SERIN):
        dirs[:] = sorted(d for d in dirs if d not in IGNORED_DIR_NAMES)
        for f in sorted(files):
            src_abs = os.path.join(root, f)
            src_rel = os.path.relpath(src_abs, PROJECT)
            dst_rel = _resolve_full_path(src_rel, segment_map)
            dst_abs = os.path.join(PROJECT, "_law_migrate_staging", os.path.relpath(dst_rel, "serin"))

            if dry_run:
                if src_rel != dst_rel:
                    print(f"  [DRY RUN] {src_rel} -> {dst_rel}")
                file_count += 1
                continue

            os.makedirs(os.path.dirname(dst_abs), exist_ok=True)
            shutil.copy2(src_abs, dst_abs)
            file_count += 1

    if dry_run:
        print(f"  ({file_count} files under serin/ would be staged)")
        if os.path.exists(staging):
            shutil.rmtree(staging)
        return

    print(f"  Staged {file_count} files. Swapping into place...")
    serin_backup = os.path.join(PROJECT, "_law_migrate_old_serin")
    if os.path.exists(serin_backup):
        shutil.rmtree(serin_backup)

    # Three-step atomic-as-possible swap: old serin/ -> backup name,
    # staging/ -> serin/, then delete the backup. Keeping the backup
    # until the very end (rather than deleting serin/ first) means a
    # crash between steps 1 and 2 still leaves a recoverable tree under
    # _law_migrate_old_serin/, not a half-deleted serin/.
    os.rename(SERIN, serin_backup)
    os.rename(staging, SERIN)
    shutil.rmtree(serin_backup)

    # git doesn't know about any of this yet — everything above used
    # plain filesystem operations, not `git mv`, specifically to avoid
    # git's own move-into-existing-directory semantics. `git add -A`
    # then lets git's own rename detection (which compares file content,
    # not paths) recognize these as renames rather than delete+add pairs,
    # which keeps `git log --follow` and blame history working.
    subprocess.run(["git", "add", "-A", "serin"], cwd=PROJECT, check=True)


def _resolve_via_applied(old_path: str, applied: dict[str, str]) -> str:
    """Resolve old_path's CURRENT on-disk location, given only the folder
    renames that have ALREADY executed earlier in this run (`applied`,
    keyed by original old_path -> fully-resolved new_path). Longest-prefix
    match, since a path can sit under at most one already-renamed ancestor
    at any given point (once that ancestor moves, its own old prefix stops
    matching anything further down the tree)."""
    if old_path in applied:
        return applied[old_path]
    for old_prefix in sorted(applied, key=len, reverse=True):
        if old_path.startswith(old_prefix + os.sep):
            return applied[old_prefix] + old_path[len(old_prefix):]
    return old_path


def _resolve_full_path(path: str, segment_map: dict[str, dict[str, str]]) -> str:
    """Resolve a filesystem path to its TRUE final form by walking every
    path segment once against segment_map.

    segment_map is keyed by DOT-JOINED MODULE PATHS (e.g.
    "serin.d1_5_ops_tooling.control_panel"), matching how
    _build_segment_map constructs it from RenameEntry.old_module. This
    function operates on and returns a SLASH-JOINED FILESYSTEM path (e.g.
    "serin/d1_5_ops_tooling/control_panel"), so every lookup converts the
    accumulated filesystem prefix to its module-path equivalent before
    querying segment_map — using slash-joined prefixes directly against a
    dot-keyed map was the exact bug in an earlier version of this
    function: every lookup silently missed, and paths came back
    unchanged with no error to signal it.

    No "applied so far" tracking is needed: this looks up each segment
    using the ORIGINAL (pre-rename) parent path as the key, which is
    exactly how the segment_map was built and exactly how a path is
    always expressed in this function's own input (module-path segments
    never appear pre-renamed inside a filesystem path string), so this
    composes every level of nesting correctly in a single pass.
    """
    parts = path.split(os.sep)
    strip_ext = parts[-1].endswith(".py")
    if strip_ext:
        parts[-1] = parts[-1][:-3]

    new_parts: list[str] = []
    old_module_prefix_so_far = ""
    for part in parts:
        replacement = segment_map.get(old_module_prefix_so_far, {}).get(part)
        new_parts.append(replacement if replacement is not None else part)
        old_module_prefix_so_far = (
            f"{old_module_prefix_so_far}.{part}" if old_module_prefix_so_far else part
        )

    if strip_ext:
        new_parts[-1] = new_parts[-1] + ".py"
    return os.sep.join(new_parts)


def _move_path(old_rel: str, new_rel: str, dry_run: bool) -> None:
    """Move a single file/folder from its fully-resolved old location to
    its fully-resolved new location. Skips no-op moves (old == new,
    which happens for files whose name was already Law-compliant but
    whose plan entry exists for some other reason — shouldn't occur in
    practice since build_plan only emits entries for actual violations,
    but checked defensively). Skips silently, with a note, if the source
    no longer exists — expected when a file's true final path already
    matches where an ancestor folder's own move placed it, so there is
    nothing left to do for that entry."""
    if old_rel == new_rel:
        return
    old_abs = os.path.join(PROJECT, old_rel)
    new_abs = os.path.join(PROJECT, new_rel)
    if not os.path.exists(old_abs):
        if os.path.exists(new_abs):
            print(f"  (already in place): {new_rel}")
        else:
            print(f"  SKIP (source missing, unexpected): {old_rel} -> {new_rel}")
        return
    print(f"  {'[DRY RUN] ' if dry_run else ''}{old_rel} -> {new_rel}")
    if dry_run:
        return
    # No os.makedirs here, deliberately. Entries are processed
    # shallowest-old-path-first (see the sort key in cmd_apply), so a
    # folder is always renamed to its final form before anything inside
    # it is processed — meaning new_parent already exists by the time we
    # get here. Pre-creating it with makedirs was the actual root cause
    # of the "duplicate nested folder" bug that took many iterations to
    # find: if a directory already exists (even empty) when you `git mv
    # X Y`, git treats Y as a destination CONTAINER and moves X *inside*
    # it as a subdirectory, rather than renaming X to Y — standard Unix
    # mv semantics, confirmed directly against a throwaway git repo.
    # Calling makedirs on a parent that's itself a pending rename target
    # created exactly that trap for the parent's own later move.
    if not os.path.isdir(os.path.dirname(new_abs)):
        raise RuntimeError(
            f"Parent directory for {new_rel} doesn't exist yet — this means "
            f"the execution order guarantee (parents renamed before "
            f"children) was violated somewhere. This should be impossible "
            f"given the sort key in cmd_apply; if you see this, that "
            f"invariant broke."
        )
    subprocess.run(["git", "mv", old_abs, new_abs], cwd=PROJECT, check=True)


def _working_tree_is_clean_enough() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"], cwd=PROJECT,
        capture_output=True, text=True, check=True,
    )
    # Allow already-staged changes from prior work (this tool doesn't
    # care about those), but nothing UNSTAGED and untracked-but-relevant,
    # since an in-progress edit could collide with an import rewrite.
    for line in result.stdout.splitlines():
        status = line[:2]
        if status[1] not in (" ",):  # second char = unstaged/untracked marker
            return False
    return True


def _run_verification() -> int:
    ok = True
    for script in ("check_structure.py", "check_imports.py"):
        result = subprocess.run(
            [sys.executable, os.path.join(PROJECT, "scripts", "law", script)],
            cwd=PROJECT, capture_output=True, text=True,
        )
        print(result.stdout)
        if result.returncode != 0:
            ok = False
    if ok:
        print("Verification passed.")
        return 0
    print(
        "Verification found remaining violations (expected if this plan "
        "didn't cover everything, e.g. File Anatomy sections). Review "
        "before committing. To revert entirely: git reset --hard HEAD"
    )
    return 1


# --- Errors ---
# (none — failures are reported via return codes and stderr messages)


if __name__ == "__main__":
    sys.exit(main())
