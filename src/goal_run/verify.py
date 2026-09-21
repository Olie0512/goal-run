from __future__ import annotations

import hashlib
import json
import os
import shlex
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from subprocess import TimeoutExpired, run

from goal_run.errors import CheckFailed
from goal_run.models import Goal

EVIDENCE_DIRNAME = ".goal-run"
EVIDENCE_FILENAME = "last-check.json"
EVIDENCE_SCHEMA = 1
DEFAULT_TIMEOUT = 300
MAX_CAPTURE = 64_000

# stdout contract for `goal-run check --json` (not the on-disk last-check.json schema)
JSON_REPORT_KEYS = ("ok", "exit_code", "checks", "evidence")
JSON_CHECK_KEYS = ("cmd", "exit_code", "ok")


def evidence_path(goal_path: Path) -> Path:
    return goal_path.parent / EVIDENCE_DIRNAME / EVIDENCE_FILENAME


def command_to_check(result: CommandResult) -> dict:
    """One `checks[]` row for `goal-run check --json`."""
    return {
        "cmd": result.cmd,
        "exit_code": int(result.exit_code),
        "ok": result.exit_code == 0,
    }


def json_report(
    *,
    ok: bool,
    exit_code: int,
    checks: list[dict] | None = None,
    evidence: str | Path | None = None,
) -> dict:
    """Stable stdout payload for `--json`. Keys stay in this order."""
    return {
        "ok": bool(ok),
        "exit_code": int(exit_code),
        "checks": list(checks or []),
        "evidence": None if evidence is None else str(evidence),
    }


def verifier_fingerprint(verifiers: list[str]) -> str:
    payload = "\n".join(cmd.strip() for cmd in verifiers)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def bind_python_executable(cmd: str) -> str:
    """Run a leading ``python`` / ``python3`` token with ``sys.executable``.

    Authors write ``python -c ...`` in GOAL.md. Some images only ship
    ``python3``. Using the interpreter that launched goal-run keeps checks
    portable and avoids a hidden second runtime.
    """
    posix = os.name != "nt"
    try:
        parts = shlex.split(cmd, posix=posix)
    except ValueError:
        return cmd
    if not parts or parts[0] not in {"python", "python3"}:
        return cmd
    parts[0] = sys.executable
    return shlex.join(parts)


def _clip(text: str) -> str:
    if len(text) <= MAX_CAPTURE:
        return text
    return text[:MAX_CAPTURE] + "\n…[truncated]…"


@dataclass
class CommandResult:
    cmd: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""


@dataclass
class Evidence:
    schema: int = EVIDENCE_SCHEMA
    ok: bool = False
    slug: str = ""
    fingerprint: str = ""
    started_at: str = ""
    finished_at: str = ""
    commands: list[CommandResult] = field(default_factory=list)

    def to_json(self) -> str:
        payload = asdict(self)
        return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    @classmethod
    def from_dict(cls, data: dict) -> Evidence:
        commands = [CommandResult(**row) for row in data.get("commands", [])]
        return cls(
            schema=int(data.get("schema", 0)),
            ok=bool(data.get("ok")),
            slug=str(data.get("slug", "")),
            fingerprint=str(data.get("fingerprint", "")),
            started_at=str(data.get("started_at", "")),
            finished_at=str(data.get("finished_at", "")),
            commands=commands,
        )


def load_evidence(path: Path) -> Evidence | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return Evidence.from_dict(data)
    except (TypeError, ValueError):
        return None


def save_evidence(path: Path, evidence: Evidence) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(evidence.to_json(), encoding="utf-8")


def clear_evidence(path: Path) -> None:
    if path.is_file():
        path.unlink()


def evidence_is_current(evidence: Evidence | None, goal: Goal) -> bool:
    if evidence is None:
        return False
    if evidence.schema != EVIDENCE_SCHEMA:
        return False
    if evidence.slug != goal.slug:
        return False
    if evidence.fingerprint != verifier_fingerprint(goal.verifiers):
        return False
    return True


def run_verifiers(
    goal: Goal,
    *,
    timeout: int = DEFAULT_TIMEOUT,
    env: dict[str, str] | None = None,
) -> Evidence:
    if not goal.verifiers:
        raise CheckFailed(
            "No verifier commands in GOAL.md. "
            "goal-run will not accept a self-grade — add a shell command under `verifier:`."
        )
    cwd = goal.path.parent if goal.path else Path.cwd()
    started = _now()
    results: list[CommandResult] = []
    ok = True
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    for cmd in goal.verifiers:
        bound = bind_python_executable(cmd)
        try:
            completed = run(
                bound,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=merged_env,
            )
            result = CommandResult(
                cmd=cmd,
                exit_code=int(completed.returncode),
                stdout=_clip(completed.stdout or ""),
                stderr=_clip(completed.stderr or ""),
            )
        except TimeoutExpired as exc:
            ok = False
            result = CommandResult(
                cmd=cmd,
                exit_code=124,
                stdout=_clip(exc.stdout or "") if isinstance(exc.stdout, str) else "",
                stderr=_clip((exc.stderr or "") if isinstance(exc.stderr, str) else "")
                + f"\nverifier timed out after {timeout}s",
            )
        if result.exit_code != 0:
            ok = False
        results.append(result)

    return Evidence(
        schema=EVIDENCE_SCHEMA,
        ok=ok,
        slug=goal.slug,
        fingerprint=verifier_fingerprint(goal.verifiers),
        started_at=started,
        finished_at=_now(),
        commands=results,
    )
