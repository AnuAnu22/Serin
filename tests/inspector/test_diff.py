"""Tests for the section diff between ctx snapshots."""
from __future__ import annotations

from tools.pipeline_inspector.diff import diff_contexts


def test_diff_detects_changed_field():
    lines = diff_contexts(
        {"halt_reason": "", "final_response": ""},
        {"halt_reason": "", "final_response": "hi there"},
    )
    assert any("final_response" in line for line in lines)


def test_diff_groups_by_section_and_shows_old_and_new():
    lines = diff_contexts(
        {"raw_response": "", "final_response": ""},
        {"raw_response": "raw one", "final_response": "final one"},
    )
    text = "\n".join(lines)
    assert "[RESPONSE]" in text
    assert "raw_response" in text and "raw one" in text
    assert "final_response" in text and "final one" in text


def test_diff_empty_when_unchanged():
    before = {"facts": [], "system_prompt": "same", "final_response": "x"}
    assert diff_contexts(before, dict(before)) == []


def test_system_prompt_rewrite_surfaces():
    # The flagship use-case: system_prompt is rebuilt between stages and the
    # old text vanishes — diff must show the change on that field.
    before = {"system_prompt": "system constraints land here",
              "response_plan": {"constraints": ["keep replies short"]}}
    after = {"system_prompt": "completely rewritten, constraint gone",
             "response_plan": {"constraints": ["keep replies short"]}}
    lines = diff_contexts(before, after)
    text = "\n".join(lines)
    assert "[PROMPT]" in text
    assert "system_prompt" in text
    # The before-state text is visible, so a human sees exactly what vanished.
    assert "system constraints land here" in text
    assert "completely rewritten" in text


def test_lists_and_dicts_compare_structurally():
    lines = diff_contexts(
        {"facts": [{"claim": "A", "belief": 0.9}]},
        {"facts": [{"claim": "A", "belief": 0.9}, {"claim": "B", "belief": 0.4}]},
    )
    assert any("facts" in line for line in lines)
