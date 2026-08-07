# Contributing to Serin

Thanks for your interest in contributing! This guide will help you get started quickly.

## Quick Start

1. **Fork and clone** the repository
2. **Install dependencies**:
   ```bash
   pip install uv
   uv sync
   ```
3. **Install pre-commit hooks** (mandatory):
   ```bash
   cp scripts/hooks/pre-commit.sh .git/hooks/pre-commit
   chmod +x .git/hooks/pre-commit
   ```
4. **Run tests**:
   ```bash
   uv run pytest tests/ -m "not integration" -q
   ```

## THE_LAW - Architectural Rules

Serin enforces strict architectural constraints. All contributions must comply:

- **5/5 Horizon**: No directory exceeds 5 files + 5 subdirectories
- **500-Line Ceiling**: No Python file exceeds 500 lines
- **Depth-Sequence Naming**: Files follow `d{depth}_{seq}_{word}_{word}.py`
- **Import DAG**: Files only import from strictly smaller depth digits
- **Required Sections**: Every file has Imports/Types/Constants/Entry/Core/Helpers/Errors

**Run local validation:**
```bash
uv run python scripts/law/check_structure.py
uv run python scripts/law/check_imports.py
```

See [THE_LAW.md](THE_LAW.md) for full specification.

## Development Workflow

1. Create a feature branch: `git checkout -b feat/my-feature`
2. Make your changes (following THE_LAW)
3. Run tests and validation locally
4. Commit with conventional format: `feat:`, `fix:`, `refactor:`, etc.
5. Push and create a pull request

## Pull Request Requirements

All PRs must:
- Pass CI checks (tests, THE_LAW validation, linting)
- Receive approval from a code owner
- Have all conversations resolved

Code owners are defined in [.github/CODEOWNERS](.github/CODEOWNERS) and auto-requested for review.

## Code Style

- Follow PEP 8 (line length: 88 characters)
- Use type hints for function signatures
- Run: `uv run ruff check .` and `uv run ruff format .`

## Testing

```bash
# Run non-integration tests
uv run pytest tests/ -m "not integration" -q

# Run specific test file
uv run pytest tests/path/to/test.py -v

# Run with coverage
uv run pytest tests/ -m "not integration" --cov=serin
```

## Need Help?

- Open a GitHub issue for bugs or features
- Use GitHub Discussions for questions

---

See also:
- [THE_LAW.md](THE_LAW.md) - Full architectural specification
- [ARCHITECTURE.md](ARCHITECTURE.md) - System design documentation
- [SECURITY.md](SECURITY.md) - Security policy
