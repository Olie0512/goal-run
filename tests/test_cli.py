from __future__ import annotations

from goal_run import __version__
from goal_run.parse import load_goal
from tests.support import copy_fixture, invoke, output_of


def test_version(runner):
    result = invoke(runner, "--version")
    assert result.exit_code == 0
    assert __version__ in result.output


def test_init_and_status(runner, tmp_path):
    goal = tmp_path / "GOAL.md"
    result = invoke(
        runner,
        "init",
        "Ship public MVP",
        "--goal",
        str(goal),
        "--verifier",
        'python -c "raise SystemExit(0)"',
    )
    assert result.exit_code == 0, result.output
    assert goal.is_file()
    assert (tmp_path / "goals" / "archive" / ".gitkeep").is_file()
    parsed = load_goal(goal)
    assert parsed.slug == "ship-public-mvp"
    assert parsed.status.value == "active"
    assert not parsed.checklist_complete

    status = invoke(runner, "status", "--goal", str(goal))
    assert status.exit_code == 0, status.output
    assert "ship-public-mvp" in status.output
    assert "0/3" in status.output
    assert "last check: (none" in status.output


def test_init_refuses_overwrite(runner, tmp_path):
    goal = copy_fixture(tmp_path, "check_pass.md")
    result = invoke(runner, "init", "again", "--goal", str(goal))
    assert result.exit_code == 1
    assert "already exists" in output_of(result)


def test_status_missing_goal(runner, tmp_path):
    result = invoke(runner, "status", "--goal", str(tmp_path / "missing.md"))
    assert result.exit_code == 1
    assert "not found" in output_of(result).lower()


def test_status_shows_last_check(runner, tmp_path):
    goal = copy_fixture(tmp_path, "check_pass.md")
    assert invoke(runner, "check", "--goal", str(goal)).exit_code == 0
    status = invoke(runner, "status", "--goal", str(goal))
    assert status.exit_code == 0
    assert "GREEN" in status.output
