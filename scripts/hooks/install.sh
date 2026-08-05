#!/usr/bin/env bash
# scripts/hooks/install.sh — install the versioned git hooks.
# Run once after cloning: bash scripts/hooks/install.sh
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
HOOK="$ROOT/.git/hooks/pre-commit"

cat >"$HOOK" <<'EOF'
#!/usr/bin/env bash
# Thin delegator — the real checks live in scripts/hooks/pre-commit.sh (versioned).
exec bash "$(git rev-parse --show-toplevel)/scripts/hooks/pre-commit.sh" "$@"
EOF
chmod +x "$HOOK"
echo "Installed pre-commit -> scripts/hooks/pre-commit.sh"
