import importlib
import sys

_module = importlib.import_module("p5_ops.1_control_panel")
sys.modules[__name__] = _module
