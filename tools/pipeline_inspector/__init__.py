"""Pipeline Inspector — drive the real MessagePipeline offline with breakpoints.

Entry points:
    python -m tools.pipeline_inspector --content "hey serin, test me"   # one-shot
    python -m tools.pipeline_inspector --content "..." --interactive      # step-mode
"""
from __future__ import annotations

from tools.pipeline_inspector.checks import (
    ALL_CHECKS,
    get_check,
    llm_produced_response,
    no_stage_error,
    planner_constraints_survive,
    register,
)
from tools.pipeline_inspector.diff import diff_contexts
from tools.pipeline_inspector.dump import dump_context, dump_snapshot
from tools.pipeline_inspector.inspector import PipelineInspector
from tools.pipeline_inspector.scenario import Scenario

__all__ = [
    "Scenario",
    "PipelineInspector",
    "dump_context",
    "dump_snapshot",
    "diff_contexts",
    "planner_constraints_survive",
    "no_stage_error",
    "llm_produced_response",
    "ALL_CHECKS",
    "get_check",
    "register",
]
