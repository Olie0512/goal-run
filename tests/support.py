from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from goal_run.cli import app

FIXTURES = Path(__file__).parent / "fixtures"


def copy_fixture(tmp_path: Path, name: str, dest_name: str = "GOAL.md") -> Path:
    dest = tmp_path / dest_name
    dest.write_text((FIXTURES / name).read_text(encoding="utf-8"), encoding="utf-8")
    return dest


def invoke(runner: CliRunner, *args: str):
    return runner.invoke(app, list(args))


def run_module(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "goal_run", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def output_of(result) -> str:
    parts = [result.output or ""]
    stderr = getattr(result, "stderr", None)
    if stderr:
        parts.append(stderr)
    if result.exception:
        parts.append(str(result.exception))
    return "\n".join(parts)
