from __future__ import annotations

import re
from pathlib import Path

import yaml

from goal_run.errors import GoalNotFoundError, GoalParseError
from goal_run.models import (
    DEFAULT_JEV_MODEL,
    DEFAULT_NOUL_MIN,
    ChecklistItem,
    Goal,
    JevConfig,
    JevQuestion,
    ProgressEntry,
    Status,
    VerifierBackend,
)

FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*\n?", re.DOTALL)
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
CHECKBOX_RE = re.compile(r"^[-*]\s+\[([ xX])\]\s+(.*\S)\s*$")
BULLET_RE = re.compile(r"^[-*]\s+(.*\S)\s*$")
PROGRESS_RE = re.compile(r"^[-*]\s+(\d{4}-\d{2}-\d{2}|date)\s*:\s+(.*\S)\s*$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FENCE_RE = re.compile(r"```(?:bash|sh|shell|zsh)?\n(.*?)```", re.DOTALL)

SECTION_ALIASES = {
    "checklist": "checklist",
    "check-list": "checklist",
    "non-goals": "non_goals",
    "non_goals": "non_goals",
    "nongoals": "non_goals",
    "progress": "progress",
    "verifier": "verifier",
    "verifiers": "verifier",
    "objective": "objective",
}


def slugify(text: str, *, fallback: str = "goal") -> str:
    lowered = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)[:60].strip("-")
    return slug or fallback


def split_frontmatter(text: str) -> tuple[dict, str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    raw_yaml = match.group(1)
    try:
        data = yaml.safe_load(raw_yaml) or {}
    except yaml.YAMLError as exc:
        raise GoalParseError(f"Invalid YAML frontmatter: {exc}") from exc
    if not isinstance(data, dict):
        raise GoalParseError("GOAL.md frontmatter must be a mapping")
    return data, text[match.end() :]


def _sections(body: str) -> dict[str, str]:
    matches = list(HEADING_RE.finditer(body))
    sections: dict[str, str] = {}
    if not matches:
        sections[""] = body.strip()
        return sections
    preamble = body[: matches[0].start()].strip()
    if preamble:
        sections[""] = preamble
    for i, match in enumerate(matches):
        raw_name = match.group(1).strip().lower()
        name = SECTION_ALIASES.get(raw_name, raw_name)
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[name] = body[match.end() : end].strip()
    return sections


def _as_str_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        lines = [line.strip() for line in value.splitlines() if line.strip()]
        return lines
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            if isinstance(item, dict):
                date = str(item.get("date", "")).strip()
                note = str(item.get("note", "")).strip()
                if date or note:
                    out.append(f"{date}: {note}".strip(": ").strip())
                continue
            text = str(item).strip()
            if text:
                out.append(text)
        return out
    raise GoalParseError(f"Expected string or list, got {type(value).__name__}")


def _parse_checkboxes(text: str) -> list[ChecklistItem]:
    items: list[ChecklistItem] = []
    for line in text.splitlines():
        match = CHECKBOX_RE.match(line.strip())
        if match:
            items.append(ChecklistItem(text=match.group(2).strip(), checked=match.group(1) != " "))
    return items


def _parse_frontmatter_checklist(value: object) -> list[ChecklistItem]:
    items: list[ChecklistItem] = []
    for raw in _as_str_list(value):
        boxed = CHECKBOX_RE.match(f"- {raw}")
        if boxed:
            items.append(ChecklistItem(text=boxed.group(2).strip(), checked=boxed.group(1) != " "))
        else:
            items.append(ChecklistItem(text=raw, checked=False))
    return items


def _parse_progress(text: str) -> list[ProgressEntry]:
    entries: list[ProgressEntry] = []
    for line in text.splitlines():
        match = PROGRESS_RE.match(line.strip())
        if match:
            entries.append(ProgressEntry(date=match.group(1), note=match.group(2).strip()))
    return entries


def _parse_frontmatter_progress(value: object) -> list[ProgressEntry]:
    if value is None:
        return []
    if isinstance(value, list):
        entries: list[ProgressEntry] = []
        for item in value:
            if isinstance(item, dict):
                date = str(item.get("date", "date")).strip() or "date"
                note = str(item.get("note", "")).strip()
                if note:
                    entries.append(ProgressEntry(date=date, note=note))
                continue
            raw = str(item).strip()
            match = PROGRESS_RE.match(f"- {raw}")
            if match:
                entries.append(ProgressEntry(date=match.group(1), note=match.group(2).strip()))
            elif raw:
                entries.append(ProgressEntry(date="date", note=raw))
        return entries
    if isinstance(value, str):
        return _parse_progress(value)
    raise GoalParseError("progress must be a list or string")


def _parse_verifiers_from_body(text: str) -> list[str]:
    commands: list[str] = []
    for fence in FENCE_RE.finditer(text):
        for line in fence.group(1).splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                commands.append(stripped)
    if commands:
        return commands
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        bullet = BULLET_RE.match(stripped)
        raw = bullet.group(1) if bullet else stripped
        if raw.startswith("[") and "]" in raw[:4]:
            continue
        commands.append(raw.strip("`").strip())
    return [cmd for cmd in commands if cmd]


def _normalize_status(value: object) -> Status:
    if value is None:
        return Status.ACTIVE
    text = str(value).strip().lower()
    try:
        return Status(text)
    except ValueError as exc:
        allowed = ", ".join(s.value for s in Status)
        raise GoalParseError(f"status must be one of: {allowed}") from exc


def _stringify_mapping_keys(value: object) -> dict:
    if not isinstance(value, dict):
        raise GoalParseError("expected a mapping")
    out: dict = {}
    for key, item in value.items():
        out[_question_id(key)] = item
    return out


def _question_id(key: object) -> str:
    if key is True:
        return "true"
    if key is False:
        return "false"
    return str(key)


def _parse_verifier_backend(value: object) -> VerifierBackend | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    try:
        return VerifierBackend(text)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in VerifierBackend)
        raise GoalParseError(f"verifier_backend must be one of: {allowed}") from exc


def _require_float(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GoalParseError(f"{field} must be a number")
    return float(value)


def _parse_jev_question(qid: str, raw: object) -> JevQuestion:
    if not qid.strip():
        raise GoalParseError("jev.questions keys must be non-empty names")
    if not isinstance(raw, dict):
        raise GoalParseError(f"jev.questions.{qid} must be a mapping")
    qtype = str(raw.get("type") or "").strip().lower()
    if qtype in {"boolean", "bool"}:
        raise GoalParseError(
            f"jev.questions.{qid}: Jev has no boolean type — use noul (calibrated yes/no)"
        )
    if qtype not in {"noul", "choice", "score"}:
        raise GoalParseError(
            f"jev.questions.{qid}: type must be noul, choice, or score (not {qtype or 'missing'!r})"
        )
    allowed = {"type", "instructions", "criteria"}
    if qtype == "noul":
        allowed.add("min")
    elif qtype == "choice":
        allowed.add("expected")
    else:
        allowed.add("min")
    extra = set(raw) - allowed
    if extra:
        names = ", ".join(sorted(str(key) for key in extra))
        raise GoalParseError(f"jev.questions.{qid}: unknown field(s): {names}")
    if "instructions" not in raw:
        raise GoalParseError(f"jev.questions.{qid}: instructions is required")
    instructions = raw["instructions"]
    if instructions is None or (isinstance(instructions, str) and not instructions.strip()):
        raise GoalParseError(f"jev.questions.{qid}: instructions is required")

    criteria = raw.get("criteria")
    min_value: float | None = None
    expected: str | None = None

    if qtype == "noul":
        if criteria is not None:
            criteria = _stringify_mapping_keys(criteria)
        min_value = (
            _require_float(raw["min"], field=f"jev.questions.{qid}.min")
            if "min" in raw
            else DEFAULT_NOUL_MIN
        )
    elif qtype == "choice":
        if not isinstance(criteria, dict) or not criteria:
            raise GoalParseError(
                f"jev.questions.{qid}: choice criteria must be a non-empty mapping"
            )
        criteria = _stringify_mapping_keys(criteria)
        if "expected" not in raw or raw["expected"] is None:
            raise GoalParseError(f"jev.questions.{qid}: choice questions require expected")
        expected = str(raw["expected"])
        if expected not in criteria:
            raise GoalParseError(
                f"jev.questions.{qid}: expected {expected!r} is not a criteria key"
            )
    else:
        if not isinstance(criteria, list) or not all(isinstance(item, str) for item in criteria):
            raise GoalParseError(
                f"jev.questions.{qid}: score criteria must be a list of strings"
            )
        if not 2 <= len(criteria) <= 10:
            raise GoalParseError(
                f"jev.questions.{qid}: score criteria must have 2–10 levels"
            )
        if "min" not in raw:
            raise GoalParseError(f"jev.questions.{qid}: score questions require min")
        min_value = _require_float(raw["min"], field=f"jev.questions.{qid}.min")

    return JevQuestion(
        id=qid,
        type=qtype,
        instructions=instructions,
        criteria=criteria,
        min_value=min_value,
        expected=expected,
    )


def _parse_jev_config(raw: object) -> JevConfig:
    if not isinstance(raw, dict):
        raise GoalParseError("jev: must be a mapping with state and questions")
    extra = set(raw) - {"model", "state", "questions"}
    if extra:
        names = ", ".join(sorted(str(key) for key in extra))
        raise GoalParseError(f"jev: unknown field(s): {names}")
    if "state" not in raw:
        raise GoalParseError("jev.state is required")
    state = raw["state"]
    if not isinstance(state, (str, dict, list)):
        raise GoalParseError("jev.state must be a string, mapping, or list")
    if isinstance(state, str) and not state.strip():
        raise GoalParseError("jev.state is empty")
    questions_raw = raw.get("questions")
    if not isinstance(questions_raw, dict) or not questions_raw:
        raise GoalParseError("jev.questions must be a non-empty mapping of named questions")
    questions = [
        _parse_jev_question(_question_id(qid), body) for qid, body in questions_raw.items()
    ]
    model = str(raw.get("model") or DEFAULT_JEV_MODEL).strip() or DEFAULT_JEV_MODEL
    return JevConfig(state=state, questions=questions, model=model)


def parse_goal_text(text: str, *, path: Path | None = None) -> Goal:
    if not text.strip():
        raise GoalParseError("GOAL.md is empty")
    fm, body = split_frontmatter(text)
    if not body.strip():
        raise GoalParseError("GOAL.md body is required (frontmatter alone is not enough)")

    sections = _sections(body)
    status = _normalize_status(fm.get("status"))
    slug = str(fm.get("slug") or "").strip()
    if not slug:
        heading = re.search(r"^#\s+(.+?)\s*$", body, re.MULTILINE)
        slug = slugify(heading.group(1) if heading else (path.stem if path else "goal"))
    slug = slugify(slug)
    if not SLUG_RE.match(slug):
        raise GoalParseError(f"slug must be kebab-case, got {slug!r}")

    objective = str(fm.get("objective") or "").strip()
    if not objective:
        objective = (sections.get("objective") or "").strip()
    if not objective:
        # First non-heading paragraph in the preamble, if any.
        preamble = sections.get("", "")
        for line in preamble.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                objective = stripped
                break
    if not objective:
        raise GoalParseError("objective is required (frontmatter or ## Objective)")

    raw_verifier = fm.get("verifier")
    if raw_verifier is None:
        raw_verifier = fm.get("verifiers")
    verifiers = _as_str_list(raw_verifier)
    if not verifiers and "verifier" in sections:
        verifiers = _parse_verifiers_from_body(sections["verifier"])

    checklist = _parse_checkboxes(sections.get("checklist", ""))
    if not checklist and "checklist" in fm:
        checklist = _parse_frontmatter_checklist(fm.get("checklist"))

    non_goals = _as_str_list(fm.get("non_goals") or fm.get("non-goals"))
    if not non_goals and "non_goals" in sections:
        non_goals = [
            BULLET_RE.match(line.strip()).group(1)
            for line in sections["non_goals"].splitlines()
            if BULLET_RE.match(line.strip())
            and not CHECKBOX_RE.match(line.strip())
        ]

    progress = _parse_frontmatter_progress(fm.get("progress"))
    if not progress and "progress" in sections:
        progress = _parse_progress(sections["progress"])

    jev = _parse_jev_config(fm["jev"]) if "jev" in fm else None
    backend = _parse_verifier_backend(fm.get("verifier_backend"))
    if backend is None:
        if jev is not None and not verifiers:
            raise GoalParseError(
                "found jev: config but verifier_backend is not 'jev'; "
                "set verifier_backend: jev (or add shell verifier commands to keep the default)"
            )
        backend = VerifierBackend.SHELL
    if backend is VerifierBackend.JEV and jev is None:
        raise GoalParseError("verifier_backend is jev but GOAL.md has no jev: block")

    return Goal(
        status=status,
        slug=slug,
        objective=objective,
        verifiers=verifiers,
        checklist=checklist,
        non_goals=non_goals,
        progress=progress,
        raw_text=text,
        path=path,
        verifier_backend=backend,
        jev=jev,
    )


def load_goal(path: Path) -> Goal:
    if not path.is_file():
        raise GoalNotFoundError(f"GOAL.md not found: {path}")
    text = path.read_text(encoding="utf-8")
    return parse_goal_text(text, path=path)


def render_goal(goal: Goal) -> str:
    verifier_yaml = "\n".join(f"  - {cmd}" for cmd in goal.verifiers) or "  - test -f GOAL.md"
    checklist = (
        "\n".join(item.markdown() for item in goal.checklist)
        or "- [ ] Replace this item with real work"
    )
    non_goals = (
        "\n".join(f"- {item}" for item in goal.non_goals) or "- (none listed)"
    )
    progress = (
        "\n".join(entry.markdown() for entry in goal.progress) or "- date: not started"
    )
    return (
        "---\n"
        f"status: {goal.status.value}\n"
        f"slug: {goal.slug}\n"
        f"objective: {goal.objective}\n"
        "verifier:\n"
        f"{verifier_yaml}\n"
        "---\n\n"
        "## Checklist\n\n"
        f"{checklist}\n\n"
        "## Non-goals\n\n"
        f"{non_goals}\n\n"
        "## Progress\n\n"
        f"{progress}\n"
    )


def upsert_frontmatter(text: str, key: str, value: str) -> str:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return f"---\n{key}: {value}\n---\n\n{text}"
    block = match.group(1)
    replaced, n = re.subn(
        rf"^{re.escape(key)}\s*:.*$",
        f"{key}: {value}",
        block,
        count=1,
        flags=re.MULTILINE,
    )
    if n == 0:
        replaced = block.rstrip() + f"\n{key}: {value}"
    return f"---\n{replaced}\n---\n{text[match.end() :]}"


def append_progress(text: str, date: str, note: str) -> str:
    line = f"- {date}: {note}"
    heading = re.search(r"^##\s+Progress\s*$", text, re.MULTILINE)
    if not heading:
        return text.rstrip() + f"\n\n## Progress\n\n{line}\n"
    after = heading.end()
    rest = text[after:]
    # Insert after the heading (and a single blank line if missing).
    if rest.startswith("\n\n"):
        insert_at = after + 2
    elif rest.startswith("\n"):
        insert_at = after + 1
        line = line + "\n"
    else:
        insert_at = after
        line = "\n" + line + "\n"
    return text[:insert_at] + line + "\n" + text[insert_at:]


def mark_completed(text: str, date: str, note: str = "completed and archived") -> str:
    return append_progress(upsert_frontmatter(text, "status", Status.COMPLETED.value), date, note)
