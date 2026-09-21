from __future__ import annotations

import json
from datetime import date as date_cls
from pathlib import Path
from typing import Annotated

import typer

from goal_run import __version__
from goal_run.archive import archive_goal
from goal_run.errors import DoneRefused, GoalError
from goal_run.models import ChecklistItem, Goal, ProgressEntry, Status, VerifierBackend
from goal_run.parse import load_goal, render_goal, slugify
from goal_run.verify import (
    DEFAULT_TIMEOUT,
    command_to_check,
    evidence_is_current,
    evidence_path,
    json_report,
    load_evidence,
    run_verifiers,
    save_evidence,
)

app = typer.Typer(
    name="goal-run",
    help="Run until done. GOAL.md + checklist + an independent verifier. No vibe-based victory.",
    no_args_is_help=True,
    add_completion=False,
)

GoalOption = Annotated[
    Path,
    typer.Option("--goal", "-g", help="Path to GOAL.md", show_default=True),
]
TimeoutOption = Annotated[
    int,
    typer.Option(
        "--timeout",
        help="Seconds per verifier command (or Jev HTTP request)",
        show_default=True,
    ),
]


def _today() -> str:
    return date_cls.today().isoformat()


def _fail(message: str, code: int = 1) -> None:
    typer.secho(message, fg=typer.colors.RED, err=True)
    raise typer.Exit(code)


def _ok(message: str) -> None:
    typer.secho(message, fg=typer.colors.GREEN)


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"goal-run {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: Annotated[
        bool | None,
        typer.Option(
            "--version",
            "-V",
            callback=version_callback,
            is_eager=True,
            help="Print version and exit",
        ),
    ] = None,
) -> None:
    """goal-run — verifier ≠ implementer."""


def _default_goal(objective: str) -> Goal:
    slug = slugify(objective)
    return Goal(
        status=Status.ACTIVE,
        slug=slug,
        objective=objective,
        verifiers=[
            (
                'python -c "import pathlib,sys; '
                "sys.exit(0 if pathlib.Path('GOAL.md').is_file() else 1)\""
            )
        ],
        checklist=[
            ChecklistItem("Replace the verifier with a command that proves this goal is done"),
            ChecklistItem("Do the work described in the objective"),
            ChecklistItem("Run `goal-run check` until it is green"),
        ],
        non_goals=[
            "Multi-agent orchestration",
            "Cloud sync, auth, or a dashboard",
            "A required model or paid API",
        ],
        progress=[ProgressEntry(date=_today(), note="initialized by goal-run")],
    )


@app.command()
def init(
    objective: Annotated[
        str | None,
        typer.Argument(help="One-sentence objective (verifiable done condition)"),
    ] = None,
    slug: Annotated[str | None, typer.Option(help="kebab-case slug")] = None,
    verifier: Annotated[
        str | None,
        typer.Option(help="Shell command that exits 0 when the goal is actually done"),
    ] = None,
    goal: GoalOption = Path("GOAL.md"),
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing GOAL.md")] = False,
) -> None:
    """Scaffold GOAL.md and goals/archive/."""
    if goal.exists() and not force:
        _fail(f"{goal} already exists (pass --force to overwrite)")
    text_objective = (objective or "Name the outcome. Done when the verifier exits 0.").strip()
    built = _default_goal(text_objective)
    if slug:
        built.slug = slugify(slug)
    if verifier:
        built.verifiers = [verifier]
    goal.parent.mkdir(parents=True, exist_ok=True)
    goal.write_text(render_goal(built), encoding="utf-8")
    archive_dir = goal.parent / "goals" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    keep = archive_dir / ".gitkeep"
    if not keep.exists():
        keep.write_text("", encoding="utf-8")
    _ok(f"wrote {goal}")
    typer.echo(f"slug: {built.slug}")
    typer.echo(f"archive dir: {archive_dir}")
    typer.echo("next: do the work, then `goal-run check`")


def _load(path: Path):
    try:
        return load_goal(path)
    except GoalError as exc:
        _fail(str(exc), exc.exit_code)


@app.command()
def status(goal: GoalOption = Path("GOAL.md")) -> None:
    """Parse and print objective, checklist, status, last verifier evidence."""
    loaded = _load(goal)
    done, total = loaded.checked_count
    typer.echo(f"goal: {loaded.slug}")
    typer.echo(f"status: {loaded.status.value}")
    typer.echo(f"objective: {loaded.objective}")
    typer.echo(f"checklist: {done}/{total}")
    if loaded.checklist:
        for item in loaded.checklist:
            mark = "x" if item.checked else " "
            typer.echo(f"  - [{mark}] {item.text}")
    if loaded.verifier_backend is VerifierBackend.JEV and loaded.jev is not None:
        typer.echo(f"verifier_backend: jev ({loaded.jev.model})")
        for question in loaded.jev.questions:
            typer.echo(f"  - {question.id}: {question.type}")
    elif loaded.verifiers:
        typer.echo("verifier:")
        for cmd in loaded.verifiers:
            typer.echo(f"  - {cmd}")
    else:
        typer.echo("verifier: (none — check/done will refuse a self-grade)")
    evidence = load_evidence(evidence_path(goal))
    if evidence_is_current(evidence, loaded) and evidence is not None:
        color = typer.colors.GREEN if evidence.ok else typer.colors.RED
        label = "GREEN" if evidence.ok else "RED"
        typer.secho(
            f"last check: {label} at {evidence.finished_at}",
            fg=color,
        )
    elif evidence is None:
        typer.echo("last check: (none — run `goal-run check`)")
    else:
        typer.echo("last check: stale (GOAL.md verifier changed — run `goal-run check`)")


def _print_evidence(evidence, *, err: bool = False) -> None:
    for i, result in enumerate(evidence.commands, start=1):
        label = "GREEN" if result.exit_code == 0 else "RED"
        color = typer.colors.GREEN if result.exit_code == 0 else typer.colors.RED
        typer.secho(
            f"[{label}] {i}/{len(evidence.commands)} exit {result.exit_code}: {result.cmd}",
            fg=color,
            err=err,
        )
        if result.stdout.strip():
            typer.echo(result.stdout.rstrip(), err=err)
        if result.stderr.strip():
            typer.secho(result.stderr.rstrip(), err=True)


def _emit_check_json(
    *,
    ok: bool,
    exit_code: int,
    checks: list[dict],
    evidence: Path | str | None,
) -> None:
    typer.echo(
        json.dumps(
            json_report(ok=ok, exit_code=exit_code, checks=checks, evidence=evidence),
            ensure_ascii=False,
        )
    )


@app.command()
def check(
    goal: GoalOption = Path("GOAL.md"),
    timeout: TimeoutOption = DEFAULT_TIMEOUT,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Machine-readable report on stdout (human text on stderr). Exit codes unchanged.",
        ),
    ] = False,
) -> None:
    """Run the verifier. Writes evidence. Refuses a self-grade with no verifier."""
    dest: Path | None = None
    checks: list[dict] = []
    try:
        loaded = load_goal(goal)
        evidence = run_verifiers(loaded, timeout=timeout)
        dest = evidence_path(goal)
        save_evidence(dest, evidence)
        checks = [command_to_check(row) for row in evidence.commands]
        process_exit = 0 if evidence.ok else 1
        if json_output:
            _emit_check_json(
                ok=evidence.ok,
                exit_code=process_exit,
                checks=checks,
                evidence=dest,
            )
        _print_evidence(evidence, err=json_output)
        typer.echo(f"evidence: {dest}", err=json_output)
        if evidence.ok:
            green_msg = (
                "GREEN — Jev verifier passed"
                if evidence.backend == VerifierBackend.JEV.value
                else "GREEN — verifier exited 0"
            )
            if json_output:
                typer.secho(green_msg, fg=typer.colors.GREEN, err=True)
            else:
                _ok(green_msg)
            return
        red_msg = (
            "RED — Jev verifier failed (this is not a self-grade)"
            if evidence.backend == VerifierBackend.JEV.value
            else "RED — verifier failed (this is not a self-grade)"
        )
        _fail(red_msg, process_exit)
    except GoalError as exc:
        if json_output:
            _emit_check_json(
                ok=False,
                exit_code=exc.exit_code,
                checks=checks,
                evidence=dest,
            )
        _fail(str(exc), exc.exit_code)


def _require_ready_for_done(loaded: Goal, goal_path: Path) -> None:
    if loaded.status is Status.BLOCKED:
        raise DoneRefused("status is blocked — unblock the goal before `done`")
    if loaded.status is Status.COMPLETED:
        raise DoneRefused("status is already completed — use `goal-run archive`")
    if not loaded.checklist:
        raise DoneRefused("checklist is empty — a goal needs at least one checkbox")
    if not loaded.checklist_complete:
        remaining = [item.text for item in loaded.checklist if not item.checked]
        listed = "\n".join(f"  - [ ] {text}" for text in remaining)
        raise DoneRefused(f"checklist incomplete ({len(remaining)} open):\n{listed}")
    if loaded.verifier_backend is VerifierBackend.JEV:
        if loaded.jev is None:
            raise DoneRefused(
                "no Jev verifier — `done` will not accept a self-grade. "
                "Add a `jev:` block with verifier_backend: jev and run `goal-run check`."
            )
    elif not loaded.verifiers:
        raise DoneRefused(
            "no verifier commands — `done` will not accept a self-grade. "
            "Add `verifier:` shell commands and run `goal-run check`."
        )
    prior = load_evidence(evidence_path(goal_path))
    if not evidence_is_current(prior, loaded) or prior is None or not prior.ok:
        raise DoneRefused(
            "no passing verifier evidence. Run `goal-run check` first "
            "(verifier ≠ implementer; ticking boxes is not enough)."
        )


@app.command()
def done(
    goal: GoalOption = Path("GOAL.md"),
    timeout: TimeoutOption = DEFAULT_TIMEOUT,
    date: Annotated[
        str | None,
        typer.Option(help="Archive date YYYY-MM-DD (defaults to today)"),
    ] = None,
) -> None:
    """Archive only when every checkbox is ticked AND the last verifier passed."""
    loaded = _load(goal)
    try:
        _require_ready_for_done(loaded, goal)
        evidence = run_verifiers(loaded, timeout=timeout)
        save_evidence(evidence_path(goal), evidence)
        _print_evidence(evidence)
        if not evidence.ok:
            _fail("RED — last verifier did not pass; refusing `done`")
        dest = archive_goal(loaded, date=date or _today())
    except GoalError as exc:
        _fail(str(exc), exc.exit_code)
    _ok(f"archived {dest}")
    typer.echo("GOAL.md removed from the working tree — start a new goal with `goal-run init`")


@app.command()
def archive(
    goal: GoalOption = Path("GOAL.md"),
    date: Annotated[
        str | None,
        typer.Option(help="Archive date YYYY-MM-DD (defaults to today)"),
    ] = None,
    force: Annotated[
        bool,
        typer.Option("--force", help="Move even if the goal is not completed"),
    ] = False,
) -> None:
    """Move GOAL.md to goals/archive/YYYY-MM-DD-<slug>.md."""
    loaded = _load(goal)
    try:
        if loaded.status is not Status.COMPLETED and not force:
            has_verifier = bool(loaded.verifiers) or (
                loaded.verifier_backend is VerifierBackend.JEV and loaded.jev is not None
            )
            if loaded.checklist_complete and has_verifier:
                prior = load_evidence(evidence_path(goal))
                if evidence_is_current(prior, loaded) and prior is not None and prior.ok:
                    dest = archive_goal(loaded, date=date or _today())
                    _ok(f"archived {dest}")
                    return
            _fail(
                "refusing to archive an unfinished goal "
                "(use `goal-run done`, or --force if you really mean it)"
            )
        dest = archive_goal(loaded, date=date or _today())
    except GoalError as exc:
        _fail(str(exc), exc.exit_code)
    _ok(f"archived {dest}")


def main() -> None:
    try:
        app()
    except GoalError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise SystemExit(exc.exit_code) from exc
