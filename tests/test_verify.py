from __future__ import annotations

import sys

from goal_run.verify import (
    JSON_CHECK_KEYS,
    JSON_REPORT_KEYS,
    CommandResult,
    bind_python_executable,
    command_to_check,
    json_report,
)


def test_bind_python_uses_running_interpreter():
    bound = bind_python_executable('python -c "raise SystemExit(2)"')
    assert bound.startswith(sys.executable)
    assert "raise SystemExit(2)" in bound


def test_bind_python3_uses_running_interpreter():
    bound = bind_python_executable("python3 -c 'print(1)'")
    assert bound.startswith(sys.executable)


def test_bind_leaves_other_commands_alone():
    assert bind_python_executable("pytest -q") == "pytest -q"
    assert bind_python_executable("true") == "true"


def test_json_report_schema_is_stable():
    payload = json_report(ok=False, exit_code=1, checks=[], evidence=None)
    assert tuple(payload) == JSON_REPORT_KEYS
    assert payload == {"ok": False, "exit_code": 1, "checks": [], "evidence": None}
    row = command_to_check(CommandResult(cmd="true", exit_code=0))
    assert tuple(row) == JSON_CHECK_KEYS
    assert row == {"cmd": "true", "exit_code": 0, "ok": True}
