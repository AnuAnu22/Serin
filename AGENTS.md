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
