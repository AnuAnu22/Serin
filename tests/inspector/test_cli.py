"""Tests for the CLI entry point (one-shot + check gating)."""
from __future__ import annotations

from tools.pipeline_inspector.checks import register
from tools.pipeline_inspector.cli import main


def test_main_prints_final_dump_and_passes_checks(capsys):
    code = main(["--content", "hey serin, test me"])
    out = capsys.readouterr().out
    assert code == 0
    assert '"final_response"' in out or "final_response" in out
    assert "CHECK PASS [planner_constraints_survive]" in out
    assert "stage_timings" in out


def test_main_failing_check_returns_nonzero(capsys):
    def always_fail(ctx):
        return "deliberate failure"

    register("_always_fail", always_fail)
    code = main(["--content", "hey serin, test me", "--checks", "_always_fail"])
    out = capsys.readouterr().out
    assert code == 1
    assert "CHECK FAIL [_always_fail]: deliberate failure" in out


def test_main_unknown_check_reports_error(capsys):
    code = main(["--content", "hey serin, test me", "--checks", "does_not_exist"])
    out = capsys.readouterr().out
    assert code == 1
    assert "unknown check" in out


def test_main_json_out_writes_final_dump(tmp_path, capsys):
    target = tmp_path / "dump.json"
    code = main(["--content", "hey serin, test me", "--json-out", str(target)])
    assert code == 0
    assert target.exists()
    assert '"final_response"' in target.read_text()
