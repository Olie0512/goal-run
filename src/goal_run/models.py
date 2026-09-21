from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

DEFAULT_JEV_MODEL = "jev-latest"
DEFAULT_NOUL_MIN = 0.8


class Status(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETED = "completed"


class VerifierBackend(StrEnum):
    SHELL = "shell"
    JEV = "jev"


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
class JevQuestion:
    """One named TypeSafe question plus local pass/fail thresholds (not sent to the API)."""

    id: str
    type: str
    instructions: object
    criteria: object | None = None
    min_value: float | None = None
    expected: str | None = None

    def api_body(self) -> dict:
        body: dict = {"type": self.type, "instructions": self.instructions}
        if self.criteria is not None:
            body["criteria"] = self.criteria
        return body


@dataclass
class JevConfig:
    state: object
    questions: list[JevQuestion]
    model: str = DEFAULT_JEV_MODEL

    def api_payload(self) -> dict:
        return {
            "model": self.model,
            "state": self.state,
            "questions": {question.id: question.api_body() for question in self.questions},
        }

    def fingerprint_payload(self) -> dict:
        return {
            "backend": VerifierBackend.JEV.value,
            "model": self.model,
            "state": self.state,
            "questions": [
                {
                    "id": question.id,
                    "type": question.type,
                    "instructions": question.instructions,
                    "criteria": question.criteria,
                    "min": question.min_value,
                    "expected": question.expected,
                }
                for question in self.questions
            ],
        }


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
    verifier_backend: VerifierBackend = VerifierBackend.SHELL
    jev: JevConfig | None = None

    @property
    def checked_count(self) -> tuple[int, int]:
        done = sum(1 for item in self.checklist if item.checked)
        return done, len(self.checklist)

    @property
    def checklist_complete(self) -> bool:
        return bool(self.checklist) and all(item.checked for item in self.checklist)
