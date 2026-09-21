from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ACTION = ROOT / ".github" / "actions" / "check" / "action.yml"
WORKFLOW = ROOT / ".github" / "workflows" / "check.yml"


def _on(data: dict):
    """GitHub `on:` is a YAML 1.1 boolean (`true`) under PyYAML."""
    return data.get("on", data.get(True))


def test_composite_action_runs_goal_run_check():
    data = yaml.safe_load(ACTION.read_text(encoding="utf-8"))
    assert data["runs"]["using"] == "composite"
    script = "\n".join(step.get("run", "") for step in data["runs"]["steps"])
    assert "python -m goal_run check" in script
    assert "--json" in script
    assert "GOAL_PATH" in script


def test_reusable_workflow_is_workflow_call_only():
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    on = _on(data)
    assert on is not None
    assert "workflow_call" in on
    assert "push" not in on
    assert "pull_request" not in on
    script = "\n".join(
        step.get("run", "")
        for job in data["jobs"].values()
        for step in job.get("steps", [])
    )
    assert "python -m goal_run check" in script
    assert "JOB_WORKFLOW_SHA" in script
