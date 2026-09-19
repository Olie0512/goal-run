"""Typed failures for the CLI (always non-zero, never a silent self-grade)."""


class GoalError(Exception):
    """User-facing failure. ``exit_code`` is what the process should return."""

    exit_code = 1


class GoalNotFoundError(GoalError):
    pass


class GoalParseError(GoalError):
    pass


class CheckFailed(GoalError):
    """Verifier command exited non-zero, or there was nothing to run."""

    pass


class DoneRefused(GoalError):
    """Checklist incomplete, blocked, or no passing verifier evidence."""

    pass


class ArchiveError(GoalError):
    pass
