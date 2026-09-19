from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class Status(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETED = "completed"


@dataclass
class ChecklistItem:
    text: str
    checked: bool = False

    def markdown(self) -> str:
        mark = "x" if self.checked else " "
        return f"- [{mark}] {self.text}"


@dataclass
class ProgressEntry:
    date: str
    note: str

    def markdown(self) -> str:
        return f"- {self.date}: {self.note}"


@dataclass
class Goal:
    status: Status
    slug: str
    objective: str
    verifiers: list[str]
    checklist: list[ChecklistItem]
    non_goals: list[str] = field(default_factory=list)
    progress: list[ProgressEntry] = field(default_factory=list)
    raw_text: str = ""
    path: Path | None = None

    @property
    def checked_count(self) -> tuple[int, int]:
        done = sum(1 for item in self.checklist if item.checked)
        return done, len(self.checklist)

    @property
    def checklist_complete(self) -> bool:
        return bool(self.checklist) and all(item.checked for item in self.checklist)
