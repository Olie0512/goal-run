from __future__ import annotations

from pathlib import Path

from goal_run.errors import ArchiveError
from goal_run.models import Goal
from goal_run.parse import mark_completed
from goal_run.verify import clear_evidence, evidence_path


def archive_filename(date: str, slug: str) -> str:
    return f"{date}-{slug}.md"


def archive_dir(goal_path: Path) -> Path:
    return goal_path.parent / "goals" / "archive"


def destination_for(goal_path: Path, date: str, slug: str) -> Path:
    return archive_dir(goal_path) / archive_filename(date, slug)


def archive_goal(goal: Goal, *, date: str, note: str = "completed and archived") -> Path:
    if goal.path is None:
        raise ArchiveError("Goal has no path; cannot archive")
    dest = destination_for(goal.path, date, goal.slug)
    if dest.exists():
        raise ArchiveError(f"Archive already exists: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    archived_text = mark_completed(goal.raw_text, date, note)
    dest.write_text(archived_text, encoding="utf-8")
    try:
        goal.path.unlink()
    except OSError as exc:
        dest.unlink(missing_ok=True)
        raise ArchiveError(f"Archived copy written but failed to remove {goal.path}: {exc}") from exc
    clear_evidence(evidence_path(goal.path))
    return dest
