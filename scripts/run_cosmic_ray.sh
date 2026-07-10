#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PACKAGE="${1:-all}"
MAX_SURVIVAL="${2:-0}"

if [ "$PACKAGE" = "all" ]; then
    CONFIG="cosmic-ray.conf"
else
    CONFIG="cosmic-ray-${PACKAGE}.conf"
fi

SESSION_DIR="$ROOT/tmp/cr-session-${PACKAGE}"
SESSION="$SESSION_DIR/session.sqlite"
mkdir -p "$SESSION_DIR"

echo "==> Config: $CONFIG"
echo "==> Session: $SESSION"
echo "==> Max survival: $MAX_SURVIVAL%"

echo "==> [1/4] baseline"
uv run cosmic-ray --verbosity INFO baseline "$CONFIG"

echo "==> [2/4] init session"
uv run cosmic-ray --verbosity INFO init "$CONFIG" "$SESSION"

echo "==> [3/4] exec"
uv run cosmic-ray --verbosity INFO exec "$CONFIG" "$SESSION"

echo "==> [4/4] score"
uv run cr-rate "$SESSION" --fail-over "$MAX_SURVIVAL"

echo "==> Done. Session saved at: $SESSION"
echo "    Re-run scoring anytime: uv run cr-rate $SESSION"
