"""Redirect — moved to p5_ops/2_hot_reloader.py."""
import importlib as _importlib
_mod = _importlib.import_module("p5_ops.2_hot_reloader")
for _attr in dir(_mod):
    if not _attr.startswith('_'):
        globals()[_attr] = getattr(_mod, _attr)
