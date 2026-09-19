from __future__ import annotations

import json

from goal_run.verify import evidence_path
from tests.support import copy_fixture, invoke, output_of


def test_check_fails_on_red_fixture(runner, tmp_path):
    goal = copy_fixture(tmp_path, "check_fail.md")
    result = invoke(runner, "check", "--goal", str(goal))
    assert result.exit_code == 1
    assert "RED" in output_of(result)
    evidence = json.loads(evidence_path(goal).read_text(encoding="utf-8"))
    assert evidence["ok"] is False
    assert evidence["commands"][0]["exit_code"] == 2


def test_check_passes_on_green_fixture(runner, tmp_path):
    goal = copy_fixture(tmp_path, "check_pass.md")
    result = invoke(runner, "check", "--goal", str(goal))
    assert result.exit_code == 0, result.output
    assert "GREEN" in result.output
    evidence = json.loads(evidence_path(goal).read_text(encoding="utf-8"))
    assert evidence["ok"] is True
    assert len(evidence["commands"]) == 2


def test_check_refuses_self_grade_without_verifier(runner, tmp_path):
    goal = copy_fixture(tmp_path, "no_verifier.md")
    result = invoke(runner, "check", "--goal", str(goal))
    assert result.exit_code == 1
    combined = output_of(result).lower()
    assert "self-grade" in combined or "verifier" in combined


def test_check_red_then_green_on_same_goal(runner, tmp_path):
    """The README demo: check fails, then the verifier is fixed, then check passes."""
    goal = copy_fixture(tmp_path, "check_fail.md")
    red = invoke(runner, "check", "--goal", str(goal))
    assert red.exit_code == 1
    text = goal.read_text(encoding="utf-8")
    goal.write_text(
        text.replace('python -c "raise SystemExit(2)"', 'python -c "raise SystemExit(0)"'),
        encoding="utf-8",
    )
    green = invoke(runner, "check", "--goal", str(goal))
    assert green.exit_code == 0, green.output
    assert "GREEN" in green.output
