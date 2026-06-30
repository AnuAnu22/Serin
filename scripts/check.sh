#!/bin/bash
set -e

echo "Checking for duplicate-content files..."
python3 scripts/find_duplicate_files.py --fail-on-match

echo "Checking for files over 500 lines..."
find . -name "*.py" -not -path "./.git/*" -not -path "./.venv/*" -not -path "*/__pycache__/*" \
  -exec wc -l {} \; | awk '$1 > 500 {print; fail=1} END {exit fail+0}'

echo "Checking imports..."
python3 -c "import serin.core.config, serin.core.logger, serin.memory.qdrant, serin.memory.store, serin.memory.evidence, serin.memory.beliefs, serin.messaging.pipeline, serin.control_panel.server"

echo "Running tests..."
DISCORD_TOKEN=test pytest tests/ -m "not integration" -q

echo "All checks passed."
