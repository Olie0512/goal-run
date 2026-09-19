from __future__ import annotations

import sys

from goal_run.verify import bind_python_executable


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
