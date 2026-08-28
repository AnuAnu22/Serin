# Serin Code Standards

## Type Annotations (Required)

Every function/method parameter and return value **must** have a type annotation. No exceptions.

```python
# GOOD
def search_memories(self, query: str, user_id: str | None = None, limit: int = 10) -> list[dict]: ...

# BAD — will be rejected
def search_memories(self, query, user_id=None, limit=10): ...
```

### Global variables

Every module-level `= None` / `= ClassName(...)` must be annotated. In the Discord gateway these live in `serin/d1_2_gateway_io/d2_1_io_discord/d3_2_discord_bot.py`:

```python
# GOOD
message_manager: EnhancedMessageManagerV3 | None = None
background_processor: BackgroundProcessor | None = None

# BAD
message_manager = None
```

### Local variables in `on_ready()`

Every `variable = ClassName(...)` must be annotated so pyright infers the type. `on_ready()` lives in `serin/d1_2_gateway_io/d2_1_io_discord/d3_1_pipeline_init/__init__.py`; component construction is delegated to `PipelineInitializer` (in `d4_1_pipeline_initializer.py`), whose instance attributes are annotated — often `Any | None` when the concrete type is not imported at init time:

```python
# GOOD
self.message_crawler: Any | None = None
memory_system: QdrantMemorySystem = QdrantMemorySystem(...)

# BAD
memory_system = QdrantMemorySystem(...)
```

### Event handlers

```python
# GOOD
async def on_message(self, message: discord.Message) -> None: ...
async def on_voice_state_update(
    self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
) -> None: ...
```

## Toolchain

The codebase uses a comprehensive static-analysis toolchain. Tools marked **CI** must pass clean before merge; the others run on a schedule or before a specific action.

### Tool Reference

| Tool | Role | Speed | Gate | Why |
|---|---|---|---|---|
| **ruff** | Lint, format, imports | ~100ms | CI | Catches F821 undefined names, syntax errors, import issues |
| **mypy** | Type checking | ~5–30s | CI | Enforces type annotations, catches missing methods, wrong kwargs |
| **pyright** | Type checking (LSP + CI) | ~3–10s | CI | Runs via Pylance in VS Code + `pyright serin/` in CI |
| **semgrep** | Custom pattern matching | ~10s | CI | Catches stale kwargs (`n_results=`), bare excepts, direct `os.environ` |
| **import-linter** | Architecture enforcement | ~2s | CI (soft)\* | Enforces THE_LAW Rule 5 layer boundaries |
| **bandit** | Security scanning | ~2s | CI | Catches hardcoded secrets, command injection, unsafe `eval()` |
| **pip-audit** | Supply-chain audit | ~5s | CI | Finds known CVEs in dependencies |
| **osv-scanner** | Supply-chain audit | ~3s | CI | Scans `pyproject.toml` for CVEs. Binary at `.tools/osv-scanner` |
| **detect-secrets** | Secret-leak prevention | ~2s | CI | Prevents accidental secret commits. Baseline at `.secrets.baseline` |
| **vulture** | Dead-code detection | ~1s | Weekly | Finds unused functions, dead branches, orphaned imports |
| **wily** | Complexity trends | ~15s | Weekly | Tracks complexity history over git commits |
| **radon** | Complexity metrics | ~1s | Per-release | Tracks Cyclomatic Complexity per function |
| **pydeps** | Dependency graph | ~5s | Before refactor | Visualizes circular imports and architectural tangles |
| **cosmic-ray** | Mutation testing | 1–4h | Pre-release | Validates test quality offline. Not per-commit |

\* `import-linter` is not currently a declared dependency; `tests/test_static_analysis.py::test_import_linter` skips when the binary is absent. Install it before treating this as a hard gate.

### Quickstart Commands

```bash
# CI gate (must pass before merge)
uv run ruff check serin/                     # Lint (fast gate, ~100ms)
uv run mypy serin/                           # Types (strict gate, ~30s)
uv run pyright serin/                        # Types (LSP gate, ~10s)
uv run semgrep --config .semgrep/rules/      # Custom patterns (~10s)
uv run import-linter lint                    # Architecture layers (~2s) — install import-linter first
uv run bandit -r serin/ -q                   # Security (~2s)
uv run pip-audit                             # Supply chain (~5s)
.tools/osv-scanner -r pyproject.toml         # Supply chain (~3s)
uv run detect-secrets scan --baseline .secrets.baseline  # Secret leak (~3s)

# Weekly / per-release
uv run vulture serin/                        # Dead code (~1s)
uv run wily build serin/ && uv run wily report serin/  # Complexity trends (~15s)
uv run radon cc serin/ -s                    # Complexity per function (~1s)
uv run pydeps serin/                         # Deps graph (~5s)

# Pre-release (offline, 1-4 hours)
uv run cosmic-ray run cosmic-ray.conf
uv run cosmic-ray report cosmic-ray.conf
```

> The CI commands above are also enforced by `tests/test_static_analysis.py` (`ruff`, `mypy`, `pyright`, `semgrep`, `import-linter`, `bandit`, `detect-secrets`). Note `bandit` is run there with `-f json -q --skip B101`.

### Ruff

Must pass clean. Key rules:
- `F821` — undefined name (`name 'models' is not defined`)
- `F405` — undefined name in `__all__`
- `E999`/`SyntaxError` — indentation errors at file level

### Mypy

Must pass clean. Configuration in `pyproject.toml` under `[tool.mypy]`:
- `strict = true` — enables all strictness flags
- `ignore_missing_imports = true` — skips third-party libs without stubs
- `follow_imports = "silent"` — only checks files we explicitly include

Annotating a `variable = ClassName(...)` in `on_ready()` lets mypy verify every method call on that variable for free — no custom test, no AST parser.

### Pyright

Configuration in `pyrightconfig.json` at project root. Catches:
- Wrong argument types (e.g., passing `str` where `int` expected)
- Missing attributes on `None` (e.g., `x.id` when `x` could be `None`)
- Import-path mismatches (e.g., a class moved between modules)
- Type inference for unannotated variables

### Semgrep

Custom rules in `.semgrep/rules/`:
- `no-bare-except.yaml` — catches bare `except:` (catches `BaseException`)
- `no-direct-env-access.yaml` — catches `os.environ[...]` outside config
- `no-eval.yaml` — catches unsafe `eval()` calls
- `no-stale-kwargs.yaml` — catches `n_results=` on `search_memories` (should be `limit=`)
- `no-deprecated-imports.yaml` — catches imports from removed modules
- `no-mood-directive.yaml` — forbids instructing the model's mood ("Current mood: …", "Be energetic and punchy") instead of letting mood be caused by real state
- `no-performative-randomness.yaml` — forbids RNG (`random.choice`, `secrets.choice`, `_rand()`, …) to fabricate personality/humanization behavior; imperfection must be caused by real accumulated state

### Import-linter

Enforces THE_LAW Rule 5 layer boundaries (see `docs/THE_LAW.md`). Logical layers and their current module prefixes:

| Logical layer | Module |
|---|---|
| config | `serin.d1_4_config_base` |
| state | `serin.d1_3_state_core` |
| pipeline | `serin.d1_1_pipeline_flow` |
| gateway | `serin.d1_2_gateway_io` |
| ops | `serin.d1_5_ops_tooling` |

A layer may only import from layers below it (toward `config`) or its own layer:
- `serin.d1_1_pipeline_flow` cannot import `serin.d1_2_gateway_io`
- `serin.d1_2_gateway_io` can import `serin.d1_1_pipeline_flow`, `serin.d1_3_state_core`, `serin.d1_4_config_base`
- `serin.d1_5_ops_tooling` can import any layer

Configuration lives in `pyproject.toml` under `[tool.importlinter]`. A few intentional violations are allow-listed via `ignore_imports`.

### Bandit

Scans for hardcoded secrets, command injection, unsafe `eval()`, and other security issues. Skip acknowledged false positives with `# nosec` on the specific line. In CI it runs with `-f json -q --skip B101`.

### Pip-audit

Scans all installed packages against the Python Vulnerability Database (PyPI advisory DB). Must pass clean before any deployment.

### OSV Scanner

Scans dependencies for known vulnerabilities using the Open Source Vulnerabilities database. Binary at `.tools/osv-scanner`.

### Detect Secrets

Prevents accidental commit of secrets (API keys, tokens, passwords). Baseline at `.secrets.baseline` whitelists known non-secrets. Update the baseline after adding legitimate secrets to config files.

### Vulture (weekly)

Finds dead code: unused functions, methods, imports, and variables. Run weekly or before major refactors.

### Wily (weekly)

Tracks complexity trends over git history. Must run on a clean repo (no dirty files). The first build creates the archive; subsequent runs compare against previous commits.

### Radon (per-release)

Reports Cyclomatic Complexity per function. Use to identify hotspots before release.

### Pydeps (before refactor)

Generates a dependency graph to visualize circular imports and architectural violations. Run before any major refactor.

### Cosmic-ray (pre-release only)

Mutation testing — runs modified versions of the code against the test suite to validate test quality. Takes 1–4 hours. Run offline before release, not per-commit.

## What NOT to Do

### No custom AST workarounds for type checking

Do not write custom AST parsers to infer types from constructor calls. **Annotate the variable.** Pyright handles it for free.

### No `type(self).method(self, ...)` delegation pattern

This causes infinite recursion. Always use inline imports:

```python
# GOOD
def start(self) -> None:
    from .audio.audio_utils import start as _start
    _start(self.audio_queue)

# BAD — infinite recursion
def start(self) -> None:
    type(self).start(self, ...)
```

### No lazy NameError

All imports must be at the top of the file. If a function uses `models`, `torch`, `numpy`, etc., import them at module level, not inside the function.

### No mismatch between file path and import path

If a class moves between modules, every `from ... import <Class>` must be updated. Pyright catches this — run it. Example: `VoiceOutputManager` now lives in `serin/d1_2_gateway_io/d2_2_voice_system/d3_4_system_output.py`, so import it from there rather than from a stale `listener`/`output` module.

## Init Pipeline Contract

`serin/d1_2_gateway_io/d2_1_io_discord/d3_1_pipeline_init/__init__.py`'s `on_ready()` is the single source of truth for component initialization. It constructs a `PipelineInitializer` and calls `await _initializer.initialize()`; the initializer's methods (`_init_message_manager`, `_init_background_processors`, `_init_voice_system`, `_build_pipeline`, …) build each component. Every component attribute (`self.message_manager`, `self.message_crawler`, etc.) must:

1. Have a type annotation (use `Any | None` when the concrete type is not imported at init time)
2. Have its `ClassName.__init__` fully annotated
3. Have every method called on it during init match the class's real method signatures

## Common Pitfalls

| Issue | Fix |
|---|---|
| `search_memories(n_results=5)` wrong kwarg | `QdrantMemorySystem.search_memories` takes `limit=`, not `n_results=` (the semgrep `no-stale-kwargs` rule enforces this) |
| Wrong import path for a moved class | Verify the class is actually exported from the module you import from (e.g. `VoiceOutputManager` → `d3_4_system_output`) |
| Missing `from __future__ import annotations` | Add at top of file to enable forward references |
| `store` parameter in extracted module functions | Type it: `store: "QdrantMemorySystem"` |
| `Optional[X]` vs `X \| None` | Use `X \| None` (Python 3.10+ union syntax) |


# AGENTS.md

## Version Control: Jujutsu (jj) — mandatory for agents

This repository uses **Jujutsu (`jj`)**, colocated with the existing Git repo
(`.jj` alongside `.git`). Human contributors can keep using plain `git`/GitHub
unchanged. **Agents must not run mutating `git` commands** (`commit`, `add`,
`checkout`, `branch`, `merge`, `rebase`, `stash`, `pull`, etc.) — use the `jj`
equivalents below instead. Read-only Git inspection (`git log`, `git show`,
`gh pr view`) is fine since jj and Git share the same underlying objects in a
colocated repo.

If `.jj` doesn't exist yet in a checkout:

```
jj git init --colocate
```

One-time per clone. Doesn't touch GitHub or what `main` looks like to Git.

This document is split into two parts: **Part 1** is the recommended workflow
for this repo. **Part 2** is a complete reference of every `jj` command and
flag referenced in project documentation, organized by topic, so nothing is
unfamiliar even if it's rarely used.

---

## Part 1 — Core mental model and workflow

### Mental model

- **No staging area, no `git add`.** The working copy *is* a commit, `@`.
  Every command auto-snapshots file changes into `@` first. New/deleted files
  are picked up automatically — nothing to "forget."
- **You're almost always editing `@` in place**, not creating a new commit,
  until you explicitly run `jj new`.
- **Two IDs per commit:** the **change ID** (stable across rewrites, e.g.
  `kntqzsqt`) and the **commit ID**/hash (changes whenever content or the
  description changes, e.g. `5d39e19d`; this is the same hash Git would show).
  Prefer change IDs when referring to work in progress.
- **Every operation is logged and reversible** via `jj op log` + `jj undo`.
  Use it instead of manually reconstructing state after a mistake.
- **Conflicts are first-class, not blocking.** A rebase that produces a
  conflict still completes, still rebases descendants, and tells you exactly
  what to run next. Don't panic or abort — read the hint jj prints.

### Standard workflow for a task

**1. Fetch and branch fresh off `main` per task:**

```
jj git fetch
jj new main -m "wip: <short description>"
```

Note: `jj git fetch` does **not** automatically import new remote bookmarks
into local ones the way `jj git clone` does — if you need to check out or test
someone else's in-progress bookmark, see "Working with other people's
bookmarks" in Part 2.

**2. Work normally.** Nothing to stage. Use `jj st` (`jj status`) and `jj diff`
often. Update the description any time with `jj describe -m "..."`, or run
bare `jj describe` to open `$EDITOR` (falls back to `nano`/`Notepad` if
`$EDITOR` isn't set) and write a longer message.

**3. Split concerns into separate commits, don't dump everything into one:**

- `jj new` — close out `@` and start the next logical commit.
- `jj squash -i` — interactively move only *some* changes from `@` back into
  its parent (opens the configured diff editor — built-in by default, or set
  `ui.diff-editor` to something like `meld`, e.g.
  `jj squash -i --tool meld` for a one-off, or a 3-way variant like
  `meld-3` for more complex merges).
- `jj split` — break an already-made commit into two or more.
- `jj diffedit -r <rev>` — edit the *content* of a commit's diff without
  checking it out; unlike `squash -i` this can change the resulting content
  state, so descendants may pick up new conflicts.

**4. Fixing something in an earlier commit:**

Decide based on how done the earlier commit is:
- If you want to review your fix with `jj diff` before folding it in: use
  `jj new <change-id>`, make the fix, inspect with `jj diff`, then
  `jj squash` to fold it into that ancestor (descendants rebase forward
  automatically, including any conflict resolutions).
- If you just want to resume editing that commit directly: `jj edit <change-id>`
  — further edits amend it in place until you `jj new` again.

To see how a change has evolved over time (message edits, squashes, rebases,
content diffs at each step): `jj evolog`. Add `-p` to see the diff at each
recorded step, which is also the recommended way to review a change's full
history instead of manually diffing two arbitrary revisions.

**5. Publishing — named bookmarks, not auto-generated:**

```
jj bookmark create <type>/<short-topic> -r @-
jj bookmark track <type>/<short-topic>
jj git push
```

Use `-r @-` when your actual work sits on the parent of an empty `@` — check
`jj log` if unsure. Naming convention: `feat/`, `fix/`, `refactor/`, `chore/`
+ kebab-case topic, matching this repo's existing commit-message style
(`refactor(foo): ...`, `feat(bar): ...`).

An alternative jj also supports — auto-generated bookmark names — exists via
`jj git push --change @-` (or `-c` for short), which generates a name like
`push-mpqrykyp`. **Don't use this for this repo**; named bookmarks keep PRs
and `jj log -r 'bookmarks()'` legible. It's documented here because it's a
real, valid option you may see referenced elsewhere.

**6. Keep history clean before review — rewrite, don't pile on:**

This repo's policy: squash/rewrite before pushing, don't stack "fix typo",
"actually fix", "address review" commits. Two documented ways to address
review comments once a bookmark is already pushed — **use the rewriting one**:

*Rewriting (this repo's preference — mirrors jj's own project and LLVM):*
```
jj new <bookmark>-      # the trailing "-" means "parent of" (revset syntax)
# make the fix; review with jj diff
jj squash
jj git push --bookmark <bookmark>   # jj force-pushes automatically when needed
```

*Adding new commits on top (documented alternative, not this repo's default —
use only if a project/reviewer explicitly asks for it):*
```
jj new <bookmark>
# make the fix; review with jj diff
jj commit -m 'address pr comments'          # creates the fix as its own commit
jj bookmark move <bookmark> --to @-         # move bookmark to the new commit
jj git push
```
or, without creating an extra commit (edit `@` directly, then move the
bookmark to `@` instead of `@-`):
```
jj new <bookmark>
# make the fix; review with jj diff
jj describe -m 'address pr comments'
jj bookmark move <bookmark> --to @
jj git push
```
Warning from upstream docs: after using this variant, run `jj new` — further
edits keep amending the same commit otherwise.

**7. Updating from `main`:**

jj has no `git pull` equivalent (open upstream issue). Do it as two steps:

```
jj git fetch
jj rebase -d main
```

If you have multiple outstanding bookmarks/stacks, rebase each one explicitly
rather than assuming one fetch/rebase covers all of them.

> **Flag note:** you may see `jj rebase -o main` in older material (`-o`/
> `--onto`) where this document uses `-d`/`--destination`. Both forms are
> documented for the destination argument depending on jj version — check
> `jj rebase --help` in your environment if a command errors, and prefer
> whichever one it accepts.

**8. Mistakes — use the operation log:**

```
jj op log      # find the operation right before things went wrong
jj undo        # undo the most recently performed operation
```

`jj undo` undoes based on the **operation log** — the whole repo state,
including bookmark moves — not just file content. Don't hand-reconstruct
state; check `jj op log` first. You can also inspect the repo as it looked at
an earlier operation without changing anything, e.g.
`jj log --at-op=<operation-id>`, or run `jj --at-op=<id> st`.

**9. Conflicts during rebase — resolve, don't avoid:**

```
jj new <conflicted-change-id>
# fix the conflict markers directly in the file, or use `jj resolve`
jj squash
```

Conflict markers look like this (from the actual conflict format):

```
<<<<<<< conflict 1 of 1
%%%%%%% diff from: <rev> "<description>" (parents of rebased revision)
\\\\\\\        to: <rev> "<description>" (rebase destination)
-<removed line>
+<added line>
+++++++ <rev> "<description>" (rebased revision)
<content from rebased revision>
>>>>>>> conflict 1 of 1 ends
```

Resolutions propagate forward automatically to descendants with the same
conflict — you typically resolve once, not once per commit it appears in.

**10. Before finishing a task — sanity check:**

```
jj log
jj log -r '(main..@) | @'
```

Confirm: clean, logically-ordered stack (not a pile of "wip"/"fix" commits);
accurate descriptions matching repo convention; nothing unintended swept in
(check `jj diff -r <rev>` per commit if unsure).

---

## Part 2 — Complete command & flag reference

Everything below is drawn directly from this repo's jj documentation set
(`jj --help` output and the GitHub/GitLab workflow guide). Included even where
not part of the standard workflow above, so nothing here is unfamiliar if it
ever comes up. Use `jj help <command>` or `jj help -k <keyword>` for anything
not detailed here — `jj help --help` lists all available keywords.

### Global options (apply to any `jj` invocation)

| Flag | Purpose |
|---|---|
| `-h`, `--help` | Print help (`-h` gives a summary) |
| `-V`, `--version` | Print version |
| `-R`, `--repository <PATH>` | Path to repo to operate on (default: closest ancestor `.jj/`) |
| `--ignore-working-copy` | Don't snapshot or update the working copy for this command |
| `--no-integrate-operation` | Create the operation as usual but don't integrate it into the op log; working copy not updated; prints the resulting operation ID (usable with `--at-operation`, `jj op restore`, or `jj op integrate`). Note: does not prevent side effects outside the repo (e.g. `jj git push --no-integrate-operation` still pushes). |
| `--ignore-immutable` | Allow rewriting commits normally protected as immutable (does not affect the `immutable_heads()` revset or `immutable` template keyword) |
| `--at-operation <ID>` (alias `--at-op`) | Load the repo as it looked at an earlier operation; implies `--ignore-working-copy`; mutating commands are technically possible here but rarely useful |
| `--debug` | Enable debug logging |
| `--color <WHEN>` | `always`, `never`, `debug`, or `auto` |
| `--quiet` | Silence non-primary output (warnings/errors still print) |
| `--no-pager` | Disable the pager |
| `--config <NAME=VALUE>` | Additional config as TOML dotted keys (repeatable) |
| `--config-file <PATH>` | Additional config file (repeatable) |

### Full top-level command list

`abandon`, `absorb`, `arrange`, `bisect`, `bookmark` (alias `b`), `commit`
(alias `ci`), `config`, `describe` (alias `desc`), `diff`, `diffedit`,
`duplicate`, `edit`, `evolog` (alias `evolution-log`), `file`, `fix`,
`gerrit`, `git`, `help`, `interdiff`, `log`, `metaedit`, `new`, `next`,
`operation` (alias `op`), `parallelize`, `prev`, `rebase`, `redo`, `resolve`,
`restore`, `revert`, `root`, `run`, `show`, `sign`, `simplify-parents`,
`sparse`, `split`, `squash`, `status` (alias `st`), `tag`, `undo`, `unsign`,
`util`, `version`, `workspace`.

Brief purpose of each, per `jj --help`:

- **abandon** — Abandon a revision (rebases descendants onto its parent(s);
  similar effect to `jj restore --changes-in`, except `abandon` gives you a
  new change while `restore` updates the existing one)
- **absorb** — Move changes from a revision into the stack of mutable
  revisions they belong to
- **arrange** — Interactively arrange the commit graph
- **bisect** — Find a bad revision by bisection (subcommand: `bisect run`)
- **bookmark** (`b`) — Manage bookmarks; subcommands: `advance`, `create`,
  `delete`, `forget`, `list`, `move`, `rename`, `set`, `track`, `untrack`
- **commit** (`ci`) — Update the description and create a new change on top
- **config** — Manage config options; subcommands: `edit`, `gc`, `get`,
  `list`, `path`, `set`, `unset`
- **describe** (`desc`) — Update the change description or other metadata
- **diff** — Compare file contents between two revisions
- **diffedit** — Touch up the content changes in a revision with a diff editor
- **duplicate** — Create new changes with the same content as existing ones
- **edit** — Set the specified revision as the working-copy revision
- **evolog** (`evolution-log`) — Show how a change has evolved over time
- **file** — File operations; subcommands: `annotate`, `chmod`, `list`,
  `search`, `show`, `track`, `untrack`
- **fix** — Update files with formatting fixes or other changes
- **gerrit** — Interact with Gerrit Code Review; subcommand: `upload`
- **git** — Commands for Git remotes and the underlying Git repo; subcommands:
  `clone`, `colocation` (with `disable`/`enable`/`status`), `export`, `fetch`,
  `import`, `init`, `push`, `remote` (with `add`/`list`/`remove`/`rename`/
  `set-url`), `root`
- **help** — Print help for a command
- **interdiff** — Show differences between the diffs of two revisions (unlike
  `jj diff --from A --to B`, which compares file content directly, `interdiff`
  compares what the changes *do*, by rebasing `--from` onto `--to`'s parents
  first — different result when the two revisions have different parents;
  `jj evolog -p` shows the whole evolution instead of just two points)
- **log** — Show revision history
- **metaedit** — Modify a revision's metadata without changing its content
- **new** — Create a new, empty change and (by default) edit it in the
  working copy
- **next** — Move the working-copy commit to the child revision (linear
  fashion; if the working copy already has visible children, `--edit` is
  implied; with `--edit`, edits the target child directly instead of creating
  a new working-copy commit on top)
- **operation** (`op`) — Work with the operation log; subcommands: `abandon`,
  `diff`, `integrate`, `log`, `restore`, `revert`, `show`
- **parallelize** — Parallelize revisions by making them siblings
- **prev** — Change the working-copy revision relative to the parent revision
- **rebase** — Move revisions to different parent(s)
- **redo** — Redo the most recently undone operation
- **resolve** — Resolve conflicted files with an external merge tool
- **restore** — Restore paths from another revision
- **revert** — Apply the reverse of the given revision(s)
- **root** — Show the current workspace root directory (shortcut for
  `jj workspace root`)
- **run** — Run a command across a set of revisions
- **show** — Show revision metadata and diff in one command
- **sign** / **unsign** — Cryptographically sign / drop a signature on a
  revision
- **simplify-parents** — Simplify parent edges for specified revision(s)
- **sparse** — Manage which paths from the working copy are present;
  subcommands: `edit`, `list`, `reset`, `set`
- **split** — Split a revision in two
- **squash** — Move changes from a revision into another revision
- **status** (`st`) — Show high-level repo status
- **tag** — Manage tags; subcommands: `delete`, `list`, `set`, `track`,
  `untrack`
- **undo** — Undo the last operation
- **util** — Infrequently used commands: `backend` (with `name`),
  `completion`, `config-schema`, `exec`, `gc`, `install-man-pages`,
  `markdown-help`, `snapshot`
- **version** — Display version information
- **workspace** — Commands for workspaces; subcommands: `add`, `forget`,
  `list`, `rename`, `root`, `update-stale`

### Rebase — both documented flag forms

The source tutorial uses `-o`/`--onto`; other project documentation uses
`-d`/`--destination` for the same destination argument (see the flag note in
Part 1, step 7 — check `jj rebase --help` in your environment if one form is
rejected):

```
jj rebase -s <source> -o <destination>     # form seen in the tutorial
jj rebase -s <source> -d <destination>     # alternate documented form
jj rebase -o <destination>                  # rebases current @ (no -s/-b/-r given)
```

`-s`/`--source` rebases the given revision and its descendants onto the
destination. `-b`/`--branch` rebases the whole "branch" relative to the
destination (default if you give a plain revision without `-s`/`-r`).

### Log, revsets, and the operation log

`jj log` shows local commits plus some remote commits for context; `~` marks
a commit with parents not included in the graph. Filter with `-r`/
`--revisions <REVSET>`.

Revset building blocks seen in project docs:

| Expression | Meaning |
|---|---|
| `@` | the working-copy commit |
| `root()` | the root commit of the repo |
| `bookmarks()` | all commits pointed to by a bookmark |
| `mine()` | commits authored by you |
| `remote_bookmarks()` | all remote-tracked bookmarks |
| `committer(email)` | commits with the given committer email |
| `all()` | every commit |
| `A \| B` | union |
| `A & B` | intersection |
| `A ~ B` | difference (A minus B) |
| `foo-` | parent(s) of `foo` |
| `foo+` | children of `foo` |
| `::foo` | ancestors of `foo` |
| `foo::` | descendants of `foo` |
| `foo::bar` | DAG range (like `git log --ancestry-path`) |
| `foo..bar` | range (like Git's `..`) |

Examples pulled directly from project docs:
```
jj log -r '@ | root() | bookmarks()'
jj log -r ::                              # equivalent to jj log -r 'all()'
jj log -r 'bookmarks() & ~(main | remote_bookmarks())'
jj log -r 'mine() & bookmarks() & ~remote_bookmarks()'
jj log -r 'remote_bookmarks() & (mine() | committer(your@email.com))'
jj log -r 'remote_bookmarks()..@'
```

Operation log:
```
jj op log                       # list all operations
jj undo                         # revert the most recent operation
jj log --at-op=<operation-id>   # view repo state as of an earlier operation
jj --at-op=<operation-id> st    # same idea for any command
```

### Git interop commands, exactly as documented

```
jj git clone <url>                              # clone; imports default remote bookmark only
jj git clone --remote upstream <url>            # clone naming the remote "upstream"
jj git init                                      # init a new jj-native-first repo
jj git init --colocate                           # colocate .jj with an existing .git
jj git fetch                                     # fetch; does NOT import new remote bookmarks to local
jj git push                                      # push tracked bookmarks
jj git push --change @-        (or -c)           # auto-generate a bookmark name and push
jj git push -c mw                                # same, naming the change "mw" -> "push-mw..."
jj git push --bookmark <name>                    # push a specific bookmark (force-pushes if needed)
jj git remote add <name> <url>                   # add a remote
jj git remote list / remove / rename / set-url   # manage remotes
jj git root                                      # show the underlying git dir (shortcut: `jj root`)
```

Git push options (`-o`/`--option`, repeatable, forwarded verbatim to the
remote/hosting platform — support is server-dependent; quote values with
spaces):

```
jj git push -o <push_option>
jj git push -o foo -o bar=val

# GitLab-specific examples from project docs:
jj git push -o ci.skip
jj git push -o 'ci.variable=MAX_RETRIES=10' -o 'ci.variable=MAX_TIME=600'
jj git push \
  -o merge_request.create \
  -o merge_request.target=main \
  -o 'merge_request.title=Add feature X' \
  -o 'merge_request.description=Implements X with tests' \
  -o merge_request.draft
jj git push \
  -o merge_request.merge_when_pipeline_succeeds \
  -o merge_request.remove_source_branch
jj git push \
  -o 'merge_request.label=label1' \
  -o 'merge_request.label=label2' \
  -o 'merge_request.unlabel=label3'
jj git push \
  -o 'merge_request.assign=user1' \
  -o 'merge_request.assign=user2' \
  -o 'merge_request.unassign=user3'
```

### Bookmarks

```
jj bookmark create <name> -r <rev>
jj bookmark track <name>
jj bookmark untrack <name>
jj bookmark move <name> --to <rev>
jj bookmark rename <old> <new>
jj bookmark delete <name>
jj bookmark forget <name>
jj bookmark list
jj bookmark advance <name>       # per jj --help subcommand list
jj bookmark set <name> -r <rev>  # per jj --help subcommand list
```

Unlike Git, bookmarks don't move automatically when you commit on top of
them — you must `jj bookmark move` (or recreate) explicitly.

Working with other people's bookmarks: `jj git fetch` doesn't import new
remote bookmarks as local ones, so to iterate on a contributor's bookmark:
```
jj new <bookmark>@<remote>
```
To auto-import all remote bookmarks (including inactive ones), set in config:
```
[remote."<name>"]
auto-track-bookmarks = "*"
```
— after which `jj new <bookmark>` works without the `@<remote>` suffix.

### Multiple remotes

```
jj git clone --remote upstream https://github.com/upstream-org/repo
cd repo
jj git remote add origin git@github.com:your-org/your-repo-fork
```

Configure default fetch/push remotes (`jj config edit --user|--repo|--workspace`):
```toml
[git]
fetch = "upstream"
push = "origin"
```
Default for both is `"origin"`. To fetch from multiple remotes by default:
```toml
[git]
fetch = ["upstream", "origin"]
push = "origin"
```

### GitHub CLI interop (relevant only for non-colocated jj repos)

This repo is colocated, so `gh` should work normally without extra setup. If
you ever work in a non-colocated jj repo, `gh` can't find the git dir on its
own (upstream issue #1008); point it there manually:
```
GIT_DIR=$(jj git root) gh issue list
```
Or automate with `direnv`: add to `.envrc`:
```
export GIT_DIR=$(jj git root)
```
then run `direnv allow` once.

### Config

```
jj config edit --user      # edit user-level config
jj config edit --repo      # edit repo-level config
jj config edit --workspace # edit workspace-level config
jj config get <key>
jj config set --user <key> <value>
jj config set --user user.name "..."
jj config set --user user.email "..."
jj config set --user ui.editor "..."
jj config set --user ui.diff-editor :builtin
jj config list
jj config unset <key>
jj config path
jj config gc
```

### File operations

```
jj file untrack <path>     # stop tracking a path (add it to .gitignore first)
jj file track <path>
jj file annotate <path>    # equivalent to git blame / hg annotate
jj file list
jj file search
jj file show
jj file chmod
```

### Everything else referenced in `jj --help` (name + one-line purpose only —
consult `jj help <command>` before first real use, since these aren't covered
by the workflow in Part 1):

- `jj absorb` — auto-distribute working-copy changes into the mutable
  ancestors they belong to, without manually picking a target commit
- `jj arrange` — interactively rearrange the commit graph
- `jj bisect` / `jj bisect run` — binary-search for a bad revision
- `jj duplicate` — copy existing changes as new changes with the same content
- `jj fix` — apply formatting/other automated fixes across files
- `jj gerrit upload` — push to Gerrit Code Review instead of GitHub/GitLab
- `jj interdiff` — diff between two revisions' *patches* rather than raw
  content (see Part 2 command list above for the detail on how this differs
  from `jj diff --from/--to`)
- `jj metaedit` — change a revision's metadata (e.g. description, author)
  without touching its content
- `jj next` / `jj prev` — move the working copy to a child/parent revision;
  `--edit` edits the target directly rather than stacking a new empty commit
- `jj parallelize` — turn a chain of revisions into siblings
- `jj redo` — redo the operation most recently undone with `jj undo`
- `jj resolve` — invoke an external merge tool on conflicted files (as an
  alternative to hand-editing conflict markers)
- `jj restore` — restore paths from another revision into the current one
  (`--changes-in` gives an effect similar to `jj abandon`, but updates the
  existing change instead of creating a new one)
- `jj revert` — apply the inverse of a given revision as a new change
- `jj run` — run a command across a set of revisions
- `jj show` — show a revision's metadata and diff in one command
- `jj sign` / `jj unsign` — cryptographically sign/unsign a revision
- `jj simplify-parents` — simplify redundant parent edges on a revision
- `jj sparse edit`/`list`/`reset`/`set` — manage sparse checkout paths
- `jj tag list`/`set`/`delete`/`track`/`untrack` — manage tags
- `jj util backend`/`backend name`/`completion`/`config-schema`/`exec`/`gc`/
  `install-man-pages`/`markdown-help`/`snapshot` — infrequently used utility
  commands (shell completions, backend info, garbage collection, etc.)
- `jj workspace add`/`forget`/`list`/`rename`/`root`/`update-stale` — manage
  multiple working-copy workspaces backed by one repo

For the operation log's `abandon`/`restore`/`revert`/`integrate` subcommands
specifically: `jj op abandon ..<id>` discards operation history up through
`<id>` (reparenting descendants onto root); to discard *recent* operations
instead, use `jj op restore <id>` followed by `jj op abandon <id>..@-`.
Abandoned operations/commits become garbage-collectable via `jj util gc`.

---

### Quick reference: Git instinct → jj equivalent

| Git instinct | jj equivalent |
|---|---|
| `git add` | nothing — automatic |
| `git commit` | `jj describe -m "..."` then `jj new`, or `jj commit -m "..."` |
| `git commit --amend` | just edit files while `@` is the commit you want to amend |
| `git checkout -b <branch>` | `jj new <base>` then `jj bookmark create <name> -r @-` |
| `git branch -f <name> <rev>` | `jj bookmark move <name> --to <rev>` |
| `git stash` | not needed — `jj new` to set work aside, `jj edit` to return |
| `git rebase -i` | `jj rebase`, `jj squash -i`, `jj split`, `jj diffedit` |
| `git pull` | `jj git fetch` then `jj rebase -d main` (or `-o main`, see flag note) |
| `git push` | `jj git push` (auto force-pushes when needed) |
| `git reflog` / `git reset --hard` | `jj op log` / `jj undo` / `jj redo` |
| `git log` | `jj log` (`-r <revset>` to filter) |
| `git blame` | `jj file annotate <path>` |
| `git bisect` | `jj bisect` |
| `git cherry-pick` | `jj duplicate`, or `jj rebase -r` onto the target |
| `git revert` | `jj revert` (or `jj abandon` if undoing your own unpushed commit) |

Full CLI reference: `jj help -k <topic>` or https://www.jj-vcs.dev/latest/cli-reference/
GitHub/GitLab workflow guide: https://www.jj-vcs.dev/latest/github/
