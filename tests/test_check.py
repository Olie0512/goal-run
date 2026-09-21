from __future__ import annotations

import json

from goal_run.verify import JSON_CHECK_KEYS, JSON_REPORT_KEYS, evidence_path
from tests.support import copy_fixture, invoke, output_of, run_module


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


def _assert_json_report(payload: dict) -> None:
    assert tuple(payload) == JSON_REPORT_KEYS
    assert isinstance(payload["ok"], bool)
    assert isinstance(payload["exit_code"], int)
    assert isinstance(payload["checks"], list)
    for row in payload["checks"]:
        assert tuple(row) == JSON_CHECK_KEYS


def _payload_from_stdout(stdout: str) -> dict:
    decoder = json.JSONDecoder()
    payload, end = decoder.raw_decode(stdout)
    assert stdout[end:].strip() == ""
    _assert_json_report(payload)
    return payload


def test_check_json_fails_on_red_fixture(tmp_path):
    goal = copy_fixture(tmp_path, "check_fail.md")
    proc = run_module("check", "--json", "--goal", str(goal))
    assert proc.returncode == 1
    payload = _payload_from_stdout(proc.stdout)
    assert payload["ok"] is False
    assert payload["exit_code"] == 1
    assert payload["checks"][0]["exit_code"] == 2
    assert payload["checks"][0]["ok"] is False
    assert payload["evidence"] == str(evidence_path(goal))
    assert "RED" not in proc.stdout
    assert "RED" in proc.stderr


def test_check_json_passes_on_green_fixture(tmp_path):
    goal = copy_fixture(tmp_path, "check_pass.md")
    proc = run_module("check", "--json", "--goal", str(goal))
    assert proc.returncode == 0, proc.stderr
    payload = _payload_from_stdout(proc.stdout)
    assert payload["ok"] is True
    assert payload["exit_code"] == 0
    assert len(payload["checks"]) == 2
    assert all(row["ok"] for row in payload["checks"])
    assert payload["evidence"] == str(evidence_path(goal))
    assert "GREEN" not in proc.stdout
    assert "GREEN" in proc.stderr


def test_check_json_refuses_self_grade_without_verifier(tmp_path):
    goal = copy_fixture(tmp_path, "no_verifier.md")
    proc = run_module("check", "--json", "--goal", str(goal))
    assert proc.returncode == 1
    payload = _payload_from_stdout(proc.stdout)
    assert payload["ok"] is False
    assert payload["exit_code"] == 1
    assert payload["checks"] == []
    assert payload["evidence"] is None
    combined = (proc.stdout + proc.stderr).lower()
    assert "self-grade" in combined or "verifier" in combined


def test_check_json_missing_goal(tmp_path):
    missing = tmp_path / "missing.md"
    proc = run_module("check", "--json", "--goal", str(missing))
    assert proc.returncode == 1
    payload = _payload_from_stdout(proc.stdout)
    assert payload["ok"] is False
    assert payload["evidence"] is None
    assert payload["checks"] == []


def test_check_json_cli_exit_matches_human_mode(runner, tmp_path):
    red_goal = copy_fixture(tmp_path, "check_fail.md", "red.md")
    green_goal = copy_fixture(tmp_path, "check_pass.md", "green.md")
    assert invoke(runner, "check", "--goal", str(red_goal)).exit_code == 1
    assert invoke(runner, "check", "--json", "--goal", str(red_goal)).exit_code == 1
    assert invoke(runner, "check", "--goal", str(green_goal)).exit_code == 0
    assert invoke(runner, "check", "--json", "--goal", str(green_goal)).exit_code == 0
