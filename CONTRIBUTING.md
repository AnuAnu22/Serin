# Contributing to Serin

Thank you for your interest in contributing to Serin! This document outlines the process and standards for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Before You Start](#before-you-start)
- [Development Setup](#development-setup)
- [THE_LAW - Architectural Rules](#the_law---architectural-rules)
- [Development Workflow](#development-workflow)
- [Commit Guidelines](#commit-guidelines)
- [Pull Request Process](#pull-request-process)
- [Testing](#testing)
- [Code Style](#code-style)

## Code of Conduct

Be respectful, inclusive, and constructive. We're all here to build something great together.

## Before You Start

Before opening a pull request:

1. Check if there's an existing issue describing the problem or feature
2. For major changes, open an issue first to discuss the approach
3. Ensure you understand the architectural constraints (THE_LAW) that govern this codebase

## Development Setup

### Prerequisites

- Python 3.11+
- Rust toolchain (for voice features)
- Discord bot token (for testing)
- Qdrant vector database (optional, for memory features)

### Quick Start

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/Serin.git
cd Serin

# Install uv (Python package manager)
pip install uv

# Install dependencies
uv sync

# Install pre-commit hooks (MANDATORY)
cp scripts/hooks/pre-commit.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# Build Rust components (required for voice features)
cd voice/rust_receiver && cargo build --release && cd ../..
cd serin_core && maturin develop --release && cd ..

# Run tests to verify setup
uv run pytest tests/ -m "not integration" -q
```

## THE_LAW - Architectural Rules

Serin enforces strict architectural constraints defined in `THE_LAW.md`. All contributions must comply with these rules, which are validated by automated checks in CI and pre-commit hooks.

### Rule 1: 5/5 Horizon

**No directory may contain more than 5 files and 5 subdirectories.**

This prevents deep nesting and forces clear organization:

```bash
# Check compliance
uv run python scripts/law/check_structure.py
```

### Rule 2: 500-Line Ceiling

**No Python file may exceed 500 lines.**

If a file grows too large, split it into multiple files at the same depth:

```bash
# Check compliance
uv run python scripts/law/check_structure.py
```

### Rule 3: Depth-Sequence Naming

**All Python files must follow the pattern: `d{depth}_{seq}_{word}_{word}.py`**

- `depth`: Numeric digit (1-5) indicating architectural depth
- `seq`: Two-digit sequence number at that depth
- `word_word`: Exactly two lowercase words separated by underscore

Examples:
- `d1_1_bot_main.py` (depth 1, sequence 01, "bot main")
- `d2_3_voice_processor.py` (depth 2, sequence 03, "voice processor")

```bash
# Check compliance
uv run python scripts/law/check_structure.py
```

### Rule 4: Required File Sections

**Every Python file must have these sections (empty ones marked `# (none)`):**

```python
"""Module docstring."""

# --- Imports ---
# (imports here)

# --- Types ---
# (type definitions)

# --- Constants ---
# (constants)

# --- Entry ---
# (public entry points)

# --- Core ---
# (main implementation)

# --- Helpers ---
# (helper functions)

# --- Errors ---
# (error classes)
```

### Rule 5: Import DAG

**Files can only import from strictly smaller depth digits.**

- Depth 1: No Python imports (only stdlib and external)
- Depth 2: Can import from depth 1
- Depth 3: Can import from depths 1-2
- And so on...

**Siblings never import each other.** Cross-branch communication must go through `d1_3_state_core/` or dependency injection.

```bash
# Check compliance
uv run python scripts/law/check_imports.py
```

### Why These Rules?

These constraints enforce:
- Clear separation of concerns
- Predictable code organization
- Shallow, navigable directory trees
- No circular dependencies
- Testable, modular architecture

See `THE_LAW.md` for the full specification.

## Development Workflow

### Branch Naming

Use descriptive branch names with a prefix:

- `feat/your-feature` - New features
- `fix/bug-description` - Bug fixes
- `refactor/component-name` - Code refactoring
- `docs/what-changed` - Documentation changes
- `test/test-name` - Test improvements

### Workflow Steps

1. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feat/my-feature
   ```

2. **Make your changes** following THE_LAW rules

3. **Run local validation**:
   ```bash
   # THE_LAW checks
   uv run python scripts/law/check_structure.py
   uv run python scripts/law/check_imports.py
   
   # Tests
   uv run pytest tests/ -m "not integration" -q
   
   # Linting
   uv run ruff check .
   ```

4. **Commit your changes** (pre-commit hooks will run automatically)

5. **Push and create a pull request**

## Commit Guidelines

### Commit Message Format

Use conventional commits:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code refactoring
- `docs`: Documentation changes
- `test`: Adding or updating tests
- `chore`: Maintenance tasks
- `perf`: Performance improvements
- `style`: Code style changes (formatting, etc.)

**Examples:**

```
feat(voice): add noise cancellation to audio processor

- Implement spectral subtraction algorithm
- Add configurable threshold parameter
- Update voice behavior to use new filter

Closes #123
```

```
fix(memory): resolve Qdrant connection timeout

The retry logic was missing exponential backoff, causing
connection storms during outages.

Fixes #456
```

### Commit Best Practices

- Make atomic commits (one logical change per commit)
- Write clear, descriptive commit messages
- Reference issues when applicable (`Closes #123`, `Fixes #456`)
- Ensure each commit passes tests (so `git bisect` works)

## Pull Request Process

### Before Opening a PR

- [ ] All tests pass locally
- [ ] THE_LAW checks pass
- [ ] Pre-commit hooks pass
- [ ] Code is linted (`uv run ruff check .`)
- [ ] Commit messages follow conventional format
- [ ] PR description is complete

### PR Requirements

All pull requests must:

1. Pass CI checks (tests, THE_LAW validation, linting)
2. Receive approval from at least one code owner
3. Have all conversations resolved

Code owners are defined in `.github/CODEOWNERS` and automatically requested for review based on changed files.

### After Approval

Squash merge is the default merge strategy. Your PR will be squashed into a single commit on `main`.

## Testing

### Running Tests

```bash
# Run all non-integration tests
uv run pytest tests/ -m "not integration" -q

# Run specific test file
uv run pytest tests/messaging/stages/test_decision.py -v

# Run with coverage
uv run pytest tests/ -m "not integration" --cov=serin --cov-report=html
```

### Integration Tests

Integration tests require live services (Discord, Qdrant, LLM endpoint) and are excluded by default:

```bash
# Run integration tests (requires live services)
uv run pytest tests/ -m "integration"
```

### Writing Tests

- Place tests in `tests/` mirroring the source structure
- Use pytest fixtures for common setup
- Mark integration tests with `@pytest.mark.integration`
- Aim for >80% coverage on new code

## Code Style

### Python

- Follow PEP 8 with some modifications
- Line length: 88 characters (Black default)
- Use type hints for function signatures
- Use docstrings for public functions and classes

### Linting and Formatting

```bash
# Check style
uv run ruff check .

# Auto-fix style issues
uv run ruff check . --fix

# Format code
uv run ruff format .
```

### Type Checking

```bash
# Run mypy
uv run mypy serin/

# Run pyright
uv run pyright serin/
```

## Getting Help

- Open a GitHub issue for bugs or feature requests
- Use GitHub Discussions for questions
- Check existing issues before opening new ones

## Recognition

All contributors are valued! Significant contributions will be recognized in the project documentation.

---

Thank you for contributing to Serin! 🎉
