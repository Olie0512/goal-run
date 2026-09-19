from __future__ import annotations

from pathlib import Path

from goal_run.parse import load_goal

ROOT = Path(__file__).resolve().parents[1]


def test_root_goal_md_parses():
    goal = load_goal(ROOT / "GOAL.md")
    assert goal.slug == "ship-v0-1-0"
    assert goal.verifiers
    assert goal.objective
    assert not goal.checklist_complete  # independent verify still open


def test_examples_parse():
    red = load_goal(ROOT / "examples" / "red.md")
    green = load_goal(ROOT / "examples" / "green.md")
    assert red.slug == "demo-red"
    assert green.slug == "demo-green"
    assert red.verifiers and green.verifiers
