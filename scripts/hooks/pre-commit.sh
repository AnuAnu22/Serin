#!/usr/bin/env bash
# scripts/hooks/pre-commit.sh — versioned pre-commit gate.
# Installed into .git/hooks/pre-commit by scripts/hooks/install.sh (thin delegator),
# so the checks themselves survive clones and are reviewable in PRs.
#
# Skip in an emergency with: git commit --no-verify
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

STAGED_FILES="$(git diff --cached --name-only --diff-filter=ACMR)"
if [ -z "$STAGED_FILES" ]; then
    echo "No staged files — nothing to check."
    exit 0
fi

fail() { echo "✗ $1" >&2; exit 1; }

echo "=== 0a. Junk-file guard (staged snapshot) ==="
# Runtime artifacts and generated state must never land in a commit.
BLOCKED='^(tmp\.txt|tmp/|\.restart\.signal|\.setup_state|\.llama_swap_ready|logs/|bot_data/|qdrant_storage/|.*\.log|.*\.db(-shm|-wal)?|.*__pycache__.*|\.ua/|graphify-out/cache/)'
if JUNK="$(echo "$STAGED_FILES" | grep -E "$BLOCKED")"; then
    echo "$JUNK"
    fail "runtime/generated artifacts staged — unstage them (git restore --staged <file>)"
fi

echo "=== 0b. Large-file guard (>2 MB) ==="
while IFS= read -r f; do
    [ -f "$f" ] || continue
    size=$(wc -c <"$f")
    if [ "$size" -gt 2097152 ]; then
        echo "$f ($((size / 1024)) KB)"
        fail "file larger than 2 MB staged — use storage outside git or add to .gitignore"
    fi
done <<<"$STAGED_FILES"

echo "=== 0c. Secrets scan (staged diff) ==="
# Only ever scans the staged additions, against the committed baseline.
if ! echo "$STAGED_FILES" | xargs -r uv run detect-secrets-hook --baseline .secrets.baseline; then
    fail "potential secret detected — audit with 'uv run detect-secrets audit .secrets.baseline'"
fi

# Checks below run against the worktree. If it differs from the index, say so
# loudly: green checks would not prove the *staged* snapshot is green.
if ! git diff --quiet; then
    echo ""
    echo "⚠ WARNING: unstaged changes present — checks validate the worktree,"
    echo "  which differs from what you are committing. Stage or stash first"
    echo "  for a trustworthy result."
    echo ""
fi

echo "=== 1. Structure (Rules 1-3) ==="
python3 scripts/law/check_structure.py

echo ""
echo "=== 2. Import DAG (Rule 5) ==="
python3 scripts/law/check_imports.py

echo ""
echo "=== 3. Ruff lint (entire repo, not just serin/) ==="
uv run ruff check .

echo ""
echo "=== 4. Test collection (catches stale imports anywhere in tests/) ==="
DISCORD_TOKEN=test uv run pytest --collect-only -q -p no:cacheprovider >/dev/null \
    || fail "pytest cannot collect the suite — a test references a dead module path"
echo "collection OK"

echo ""
echo "=== 5. Import integrity (every module loads) ==="
DISCORD_TOKEN=test uv run pytest tests/test_runtime_contracts.py -q -p no:cacheprovider

echo ""
echo "=== 6. Pipeline smoke tests ==="
DISCORD_TOKEN=test uv run pytest tests/test_pipeline_smoke.py -q -p no:cacheprovider

echo ""
echo "=== 7. Bandit security (serin, full profile; entry launchers, reduced) ==="
uv run bandit -q -r serin/
# Launchers spawn fixed hardcoded commands (docker/cargo) and poll localhost:
# B404/B603/B607/B310 are informational noise there; everything else still applies.
uv run bandit -q --skip B404,B603,B607,B310 discord_bot.py hot_reloader.py

echo ""
echo "=== 8. Semgrep patterns ==="
uv run semgrep --config .semgrep/rules/ --quiet --error serin/

echo ""
echo "=== All checks pass ==="
