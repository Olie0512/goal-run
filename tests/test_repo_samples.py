from __future__ import annotations

from pathlib import Path

from goal_run.models import VerifierBackend
from goal_run.parse import load_goal

ROOT = Path(__file__).resolve().parents[1]


def test_root_goal_md_parses():
    goal = load_goal(ROOT / "GOAL.md")
    assert goal.slug == "ship-v0-1-0"
    assert goal.verifiers
    assert goal.objective
    assert goal.verifier_backend is VerifierBackend.SHELL
    assert not goal.checklist_complete  # independent verify still open


def test_examples_parse():
    red = load_goal(ROOT / "examples" / "red.md")
    green = load_goal(ROOT / "examples" / "green.md")
    jev = load_goal(ROOT / "examples" / "jev.md")
    assert red.slug == "demo-red"
    assert green.slug == "demo-green"
    assert jev.slug == "jev-opt-in-demo"
    assert red.verifiers and green.verifiers
    assert red.verifier_backend is VerifierBackend.SHELL
    assert green.verifier_backend is VerifierBackend.SHELL
    assert jev.verifier_backend is VerifierBackend.JEV
    assert jev.jev is not None
    assert [q.id for q in jev.jev.questions] == ["is_demo", "kind", "clarity"]
