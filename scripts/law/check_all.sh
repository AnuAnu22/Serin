#!/usr/bin/env bash
# scripts/law/check_all.sh — Run all Law compliance checks + tests.
# Exit 0 = all pass, exit 1 = any failure.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== 1. Structure check (Rules 1, 2, 3) ==="
python3 "$SCRIPT_DIR/check_structure.py"

echo ""
echo "=== 2. Import check (Rule 5) ==="
python3 "$SCRIPT_DIR/check_imports.py"

echo ""
echo "=== 3. Tests ==="
cd "$PROJECT_DIR"
DISCORD_TOKEN=test python3 -m pytest tests/ -m "not integration" \
    --ignore=tests/integration \
    --ignore=tests/test_vision.py \
    --ignore=tests/messaging/test_processor.py \
    -q 2>&1

echo ""
echo "=== All checks passed ==="
