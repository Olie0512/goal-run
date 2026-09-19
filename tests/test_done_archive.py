from __future__ import annotations

from goal_run.parse import load_goal
from goal_run.verify import evidence_path

from .conftest import copy_fixture, invoke, output_of


def test_done_refuses_open_checklist_even_after_green_check(runner, tmp_path):
    goal = copy_fixture(tmp_path, "incomplete.md")
    assert invoke(runner, "check", "--goal", str(goal)).exit_code == 0
    result = invoke(runner, "done", "--goal", str(goal), "--date", "2026-09-19")
    assert result.exit_code == 1
    assert "checklist incomplete" in output_of(result)
    assert goal.is_file()


def test_done_refuses_without_evidence(runner, tmp_path):
    goal = copy_fixture(tmp_path, "ready_for_done.md")
    result = invoke(runner, "done", "--goal", str(goal), "--date", "2026-09-19")
    assert result.exit_code == 1
    assert "evidence" in output_of(result).lower()
    assert goal.is_file()


def test_done_refuses_blocked(runner, tmp_path):
    goal = copy_fixture(tmp_path, "blocked.md")
    assert invoke(runner, "check", "--goal", str(goal)).exit_code == 0
    result = invoke(runner, "done", "--goal", str(goal))
    assert result.exit_code == 1
    assert "blocked" in output_of(result)


def test_done_refuses_empty_checklist(runner, tmp_path):
    goal = copy_fixture(tmp_path, "empty_checklist.md")
    assert invoke(runner, "check", "--goal", str(goal)).exit_code == 0
    result = invoke(runner, "done", "--goal", str(goal))
    assert result.exit_code == 1
    assert "empty" in output_of(result)


def test_done_archives_when_boxes_and_verifier_are_green(runner, tmp_path):
    goal = copy_fixture(tmp_path, "ready_for_done.md")
    assert invoke(runner, "check", "--goal", str(goal)).exit_code == 0
    result = invoke(runner, "done", "--goal", str(goal), "--date", "2026-09-19")
    assert result.exit_code == 0, result.output
    dest = tmp_path / "goals" / "archive" / "2026-09-19-ready-for-done.md"
    assert dest.is_file()
    assert not goal.exists()
    assert not evidence_path(goal).exists()
    archived = load_goal(dest)
    assert archived.status.value == "completed"
    assert "archived" in result.output


def test_archive_refuses_unfinished(runner, tmp_path):
    goal = copy_fixture(tmp_path, "incomplete.md")
    result = invoke(runner, "archive", "--goal", str(goal))
    assert result.exit_code == 1
    assert goal.is_file()


def test_archive_force(runner, tmp_path):
    goal = copy_fixture(tmp_path, "incomplete.md")
    result = invoke(runner, "archive", "--goal", str(goal), "--date", "2026-09-19", "--force")
    assert result.exit_code == 0, result.output
    dest = tmp_path / "goals" / "archive" / "2026-09-19-incomplete-goal.md"
    assert dest.is_file()
    assert not goal.exists()
