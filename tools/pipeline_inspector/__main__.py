"""Allow ``python -m tools.pipeline_inspector``."""
from __future__ import annotations

import sys

from tools.pipeline_inspector.cli import main

if __name__ == "__main__":
    sys.exit(main())
