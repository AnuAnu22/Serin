"""Redirect — moved to p5_ops/3_duplicate_finder.py."""
import importlib as _importlib
import sys as _sys
_mod = _importlib.import_module("p5_ops.3_duplicate_finder")
# Re-export the main function so scripts can still work
main = _mod.main
if __name__ == "__main__":
    _sys.exit(main())
