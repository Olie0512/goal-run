from __future__ import annotations

import pytest

from goal_run.errors import GoalParseError
from goal_run.models import Status
from goal_run.parse import load_goal, parse_goal_text, slugify

from .conftest import FIXTURES


@pytest.mark.parametrize(
    ("name", "slug", "status", "checked", "total", "n_verifiers"),
    [
        ("check_fail.md", "check-fail", Status.ACTIVE, 1, 2, 1),
        ("check_pass.md", "check-pass", Status.ACTIVE, 1, 2, 2),
        ("incomplete.md", "incomplete-goal", Status.ACTIVE, 1, 3, 1),
        ("ready_for_done.md", "ready-for-done", Status.ACTIVE, 3, 3, 1),
        ("no_verifier.md", "no-verifier", Status.ACTIVE, 2, 2, 0),
        ("blocked.md", "blocked-goal", Status.BLOCKED, 2, 2, 1),
        ("empty_checklist.md", "empty-checklist", Status.ACTIVE, 0, 0, 1),
        ("frontmatter_schema.md", "frontmatter-schema", Status.ACTIVE, 1, 3, 1),
    ],
)
def test_fixtures_parse(name, slug, status, checked, total, n_verifiers):
    goal = load_goal(FIXTURES / name)
    assert goal.slug == slug
    assert goal.status is status
    assert goal.checked_count == (checked, total)
    assert len(goal.verifiers) == n_verifiers
    assert goal.objective


def test_frontmatter_progress_and_nongoals():
    goal = load_goal(FIXTURES / "frontmatter_schema.md")
    assert goal.non_goals == ["SaaS", "star fraud"]
    assert [entry.note for entry in goal.progress] == [
        "yaml progress row",
        "string progress row",
    ]
    assert goal.checklist[0].checked is False
    assert goal.checklist[1].checked is True
    assert goal.checklist[2].text == "plain item defaults to open"


def test_empty_file_rejected():
    with pytest.raises(GoalParseError, match="empty"):
        parse_goal_text("   \n")


def test_frontmatter_only_rejected():
    with pytest.raises(GoalParseError, match="body is required"):
        parse_goal_text("---\nstatus: active\nslug: x\nobjective: nope\nverifier: true\n---\n")


def test_bad_status_rejected():
    with pytest.raises(GoalParseError, match="status"):
        parse_goal_text("---\nstatus: vibes\nslug: x\nobjective: o\n---\n\n## Checklist\n\n- [ ] a\n")


def test_slugify():
    assert slugify("Ship public MVP") == "ship-public-mvp"
    assert slugify("!!!") == "goal"


def test_body_verifier_fence():
    text = """---
status: active
slug: fence
objective: Use a fenced verifier.
---

## Verifier

```bash
python -c "raise SystemExit(0)"
# comment
python -c "print(1)"
```

## Checklist

- [ ] one
"""
    goal = parse_goal_text(text)
    assert goal.verifiers == [
        'python -c "raise SystemExit(0)"',
        "python -c \"print(1)\"",
    ]
