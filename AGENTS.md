# Serin Code Standards

## Type Annotations (Required)

Every function/method parameter and return value **must** have a type annotation. No exceptions.

```python
# GOOD
def search_memories(self, query: str, user_id: str | None = None, limit: int = 10) -> list[dict]: ...

# BAD — will be rejected
def search_memories(self, query, user_id=None, limit=10): ...
```

### Global variables in bot.py

Every module-level `= None` / `= ClassName(...)` must be annotated:

```python
# GOOD
message_manager: EnhancedMessageManagerV3 | None = None
background_processor: BackgroundProcessor | None = None

# BAD
message_manager = None
```

### Local variables in bot_pipeline_init.py on_ready()

Every `variable = ClassName(...)` must be annotated so pyright infers the type:

```python
# GOOD
memory_system: QdrantMemorySystem = QdrantMemorySystem(...)
message_crawler: MessageCrawler = MessageCrawler(client, memory_system, ...)

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

The codebase uses a comprehensive static analysis toolchain. Every tool must pass clean before merge.

### Tool Reference

| Tool | Role | Speed | Gate | Why |
|---|---|---|---|---|
| **ruff** | Linting, format, imports | ~100ms | CI | Catches F821 undefined names, syntax errors, import issues |
| **mypy** | Type checking | ~5-30s | CI | Enforces type annotations, catches missing methods, wrong kwargs |
| **pyright** | Type checking (LSP + CI) | ~3-10s | CI | Runs via Pylance in VS Code + `pyright serin/` in CI |
| **semgrep** | Custom pattern matching | ~10s | CI | Catches stale kwargs (`n_results=`), bare excepts, direct `os.environ` |
| **import-linter** | Architecture enforcement | ~2s | CI | Enforces THE_LAW.md Rule 5 layer boundaries |
| **bandit** | Security scanning | ~2s | CI | Catches hardcoded secrets, command injection, unsafe `eval()` |
| **pip-audit** | Supply chain audit | ~5s | CI | Finds known CVEs in dependencies |
| **osv-scanner** | Supply chain audit (Go) | ~3s | CI | Scans lockfile for CVEs. Binary at `.tools/osv-scanner` |
| **detect-secrets** | Secret leak prevention | ~2s | CI | Prevents accidental secret commits. Baseline at `.secrets.baseline` |
| **vulture** | Dead code detection | ~1s | Weekly | Finds unused functions, dead branches, orphaned imports |
| **wily** | Complexity trends | ~15s | Weekly | Tracks complexity history over git commits |
| **radon** | Complexity metrics | ~1s | Per-release | Tracks Cyclomatic Complexity per function |
| **pydeps** | Dependency graph | ~5s | Before refactor | Visualizes circular imports and architectural tangles |
| **cosmic-ray** | Mutation testing | ~1-4h | Pre-release | Validates test quality offline. Not per-commit |

### Quickstart Commands

```bash
# CI gate (must pass before merge)
uv run ruff check serin/                     # Lint (fast gate, ~100ms)
uv run mypy serin/                           # Types (strict gate, ~30s)
uv run pyright serin/                        # Types (LSP gate, ~10s)
uv run semgrep --config .semgrep/rules/      # Custom patterns (~10s)
.venv/bin/import-linter lint                  # Architecture layers (~2s)
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

### Ruff

```bash
uv run ruff check serin/
```

Must pass clean. Key rules:
- `F821` — undefined name (`name 'models' is not defined`)
- `F405` — undefined name in `__all__`
- `E999`/`SyntaxError` — indentation errors at file level

### Mypy

```bash
uv run mypy serin/
```

Must pass clean. Configuration in `pyproject.toml`:
- `strict = true` — enables all strictness flags
- `ignore_missing_imports = true` — skips third-party libs without stubs
- `follow_imports = "silent"` — only checks files we explicitly include

Annotating a `variable = ClassName(...)` in `on_ready()` lets mypy verify every method call on that variable for free — no custom test, no AST parser.

### Pyright

```bash
uv run pyright serin/
```

Configuration in `pyrightconfig.json` at project root. Catches:
- Wrong argument types (e.g., passing `str` where `int` expected)
- Missing attributes on None (e.g., `x.id` when `x` could be `None`)
- Import path mismatches (e.g., `from .listener import VoiceOutputManager` after class moved)
- Type inference for unannotated variables

### Semgrep

```bash
uv run semgrep --config .semgrep/rules/
```

Custom rules in `.semgrep/rules/`:
- `no-bare-except.yaml` — catches bare `except:` (catches `BaseException`)
- `no-direct-env-access.yaml` — catches `os.environ[...]` outside config
- `no-eval.yaml` — catches unsafe `eval()` calls
- `no-stale-kwargs.yaml` — catches `n_results=` (should be `limit=`)
- `no-deprecated-imports.yaml` — catches imports from removed modules

### Import-linter

```bash
.venv/bin/import-linter lint
```

Configuration in `pyproject.toml` under `[tool.import_linter]`. Enforces THE_LAW.md Rule 5:
- config → state → pipeline → gateway → ops
- A layer can only import from layers above it (lower index) or same layer
- E.g., `serin.pipeline` cannot import `serin.gateway`
- E.g., `serin.gateway` can import `serin.pipeline`, `serin.state`, `serin.config`
- E.g., `serin.ops` can import any layer

### Bandit

```bash
uv run bandit -r serin/ -f json -q
```

Scans for hardcoded secrets, command injection, unsafe `eval()`, and other security issues. Skip false positives with `# nosec` on specific lines.

### Pip-audit

```bash
uv run pip-audit
```

Scans all installed packages against the Python Vulnerability Database (PyPI advisory DB). Must pass clean before any deployment.

### OSV Scanner

```bash
.tools/osv-scanner -r pyproject.toml
```

Scans dependencies for known vulnerabilities using the Open Source Vulnerabilities database. Binary at `.tools/osv-scanner`.

### Detect Secrets

```bash
uv run detect-secrets scan --baseline .secrets.baseline
```

Prevents accidental commit of secrets (API keys, tokens, passwords). Baseline at `.secrets.baseline` whitelists known non-secrets. Update baseline after adding legitimate secrets to config files.

### Vulture (weekly)

```bash
uv run vulture serin/
```

Finds dead code: unused functions, methods, imports, and variables. Run weekly or before major refactors.

### Wily (weekly)

```bash
uv run wily build serin/ && uv run wily report serin/
```

Tracks complexity trends over git history. Must run on a clean repo (no dirty files). First build creates the archive; subsequent runs compare against previous commits.

### Radon (per-release)

```bash
uv run radon cc serin/ -s
```

Reports Cyclomatic Complexity per function. Use to identify hotspots before release.

### Pydeps (before refactor)

```bash
uv run pydeps serin/
```

Generates a dependency graph to visualize circular imports and architectural violations. Run before any major refactor.

### Cosmic-ray (pre-release only)

```bash
uv run cosmic-ray run cosmic-ray.conf
uv run cosmic-ray report cosmic-ray.conf
```

Mutation testing — runs modified versions of the code against the test suite to validate test quality. Takes 1-4 hours. Run offline before release, not per-commit.

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

If `VoiceOutputManager` moves from `listener.py` to `output.py`, every `from .listener import VoiceOutputManager` must be updated. Pyright catches this — run it.

## Init Pipeline Contract

`serin/gateway/discord/bot_pipeline_init.py`'s `on_ready()` is the single source of truth for all component initialization. Every `variable = ClassName(...)` must:

1. Have a type annotation
2. Have its `ClassName.__init__` fully annotated
3. Have every method called on `variable` during init match the class's real method signatures

## Common Pitfalls

| Issue | Fix |
|---|---|
| `search_memories(n_results=5)` wrong kwarg | Check the method signature first — it might be `limit=` instead |
| `from listener import VoiceOutputManager` wrong path | Verify the class is actually exported from that module |
| Missing `from __future__ import annotations` | Add at top of file to enable forward references |
| `store` parameter in extracted module functions | Type it: `store: "QdrantMemorySystem"` |
| `Optional[X]` vs `X \| None` | Use `X \| None` (Python 3.10+ union syntax) |
