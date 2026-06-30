"""Redirect — moved to p5_ops/4_database_protector.py. Update your imports."""
import importlib as _importlib
_mod = _importlib.import_module("p5_ops.4_database_protector")
DatabaseProtector = _mod.DatabaseProtector
DatabaseValidationError = _mod.DatabaseValidationError
DatabaseRecoveryError = _mod.DatabaseRecoveryError
get_database_protector = _mod.get_database_protector
