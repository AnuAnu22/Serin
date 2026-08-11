"""Section diff between two ctx snapshots.

Compares two production-cipher snapshots (as captured by ``PipelineInspector``)
field-by-field, grouped by the same MessageContext sections as dump. Each
changed field renders as ``field: old -> new`` with truncated values, so a
question like "did PromptAssemblyStage's system_prompt survive into LLMCallStage"
is answered by diffing the two boundary snapshots — no manual trace.
"""
from __future__ import annotations

import json
from typing import Any

from tools.pipeline_inspector.dump import SECTIONS


def _show(value: Any) -> str:
    if isinstance(value, str):
        if len(value) > 120:
            return value[:120] + "…"
        return value
    if isinstance(value, (dict, list)):
        text = json.dumps(value, default=str, ensure_ascii=False)
        if len(text) > 160:
            return text[:160] + "…"
        return text
    return repr(value)


def diff_contexts(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Lines describing fields that differ, grouped by section.

    Only fields whose value changed are reported, so an unchanged context
    yields an empty list.
    """
    lines: list[str] = []
    for section, fields in SECTIONS.items():
        changed = [
            (field, before.get(field), after.get(field))
            for field in fields
            if before.get(field) != after.get(field)
        ]
        if not changed:
            continue
        lines.append(f"[{section}]")
        for field, old, new in changed:
            lines.append(f"  {field}: {_show(old)}")
            lines.append(f"    -> {_show(new)}")
    return lines


__all__ = ["diff_contexts"]
