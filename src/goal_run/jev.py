"""Optional TypeSafe Jev verifier (opt-in). Default installs never import-call this path.

HTTP uses stdlib urllib only — no typesafe-sdk dependency. The API key is read from
``TYPESAFE_API_KEY`` at check time and must never be written to evidence or logs.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field

from goal_run import __version__
from goal_run.models import DEFAULT_NOUL_MIN, Goal, JevConfig, JevQuestion

SYSTEMONE_URL = "https://api.typesafe.ai/v1/systemone"
API_KEY_ENV = "TYPESAFE_API_KEY"

ANSWER_PUBLIC_KEYS = (
    "type",
    "noul",
    "choice",
    "score",
    "confidence",
    "probabilities",
    "legend",
)
USAGE_PUBLIC_KEYS = ("input_tokens", "output_tokens", "cost_usd")

_BEARER_RE = re.compile(r"(?i)(bearer\s+)\S+")
_KEY_ASSIGN_RE = re.compile(r"(?i)(TYPESAFE_API_KEY\s*[=:]\s*)\S+")

SystemoneRequest = Callable[[dict, str, int], tuple[int, str]]


@dataclass
class JevQuestionOutcome:
    id: str
    ok: bool
    summary: str
    detail: dict = field(default_factory=dict)
    error: str = ""


@dataclass
class JevEvaluation:
    ok: bool
    model: str | None = None
    usage: dict | None = None
    answers: dict | None = None
    outcomes: list[JevQuestionOutcome] = field(default_factory=list)
    transport_error: str | None = None


class _FailClosedRedirects(urllib.request.HTTPRedirectHandler):
    """Redirects are fail-closed so a 3xx cannot bounce the Bearer token elsewhere."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(
            req.full_url,
            code,
            f"redirects are fail-closed ({code})",
            headers,
            fp,
        )


def redact_secrets(text: str, api_key: str | None = None) -> str:
    """Strip credentials from text that might land in evidence or stderr."""
    if api_key:
        text = text.replace(api_key, "[redacted]")
    text = _BEARER_RE.sub(r"\1[redacted]", text)
    return _KEY_ASSIGN_RE.sub(r"\1[redacted]", text)


def public_answer(answer: object) -> dict:
    if not isinstance(answer, dict):
        return {"value": answer}
    return {key: answer[key] for key in ANSWER_PUBLIC_KEYS if key in answer}


def public_usage(usage: object) -> dict | None:
    if not isinstance(usage, dict):
        return None
    out = {key: usage[key] for key in USAGE_PUBLIC_KEYS if key in usage}
    return out or None


def public_answers(answers: object) -> dict | None:
    if not isinstance(answers, dict):
        return None
    return {str(qid): public_answer(payload) for qid, payload in answers.items()}


def systemone_request(payload: dict, api_key: str, timeout: int) -> tuple[int, str]:
    """POST ``/v1/systemone``. Returns ``(status_code, body_text)``. Never logs the key."""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        SYSTEMONE_URL,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"goal-run/{__version__}",
        },
    )
    opener = urllib.request.build_opener(_FailClosedRedirects())
    try:
        with opener.open(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            status = int(getattr(resp, "status", None) or resp.getcode())
            return status, body
    except urllib.error.HTTPError as exc:
        raw = exc.read() if exc.fp else b""
        body = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        return int(exc.code), body


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def evaluate_question(question: JevQuestion, answer: object) -> JevQuestionOutcome:
    if not isinstance(answer, dict):
        return JevQuestionOutcome(
            id=question.id,
            ok=False,
            summary=f"jev:{question.id} ({question.type})",
            error="answer missing or not an object",
        )
    detail = public_answer(answer)
    announced = str(answer.get("type") or "").strip().lower()
    if announced and announced != question.type:
        return JevQuestionOutcome(
            id=question.id,
            ok=False,
            summary=f"jev:{question.id} ({question.type})",
            detail=detail,
            error=f"answer type {announced!r} did not match question type {question.type!r}",
        )

    if question.type == "noul":
        noul = _as_float(answer.get("noul"))
        minimum = question.min_value if question.min_value is not None else DEFAULT_NOUL_MIN
        if noul is None:
            return JevQuestionOutcome(
                id=question.id,
                ok=False,
                summary=f"jev:{question.id} (noul >= {minimum})",
                detail=detail,
                error="noul answer was not a number",
            )
        ok = noul >= minimum
        return JevQuestionOutcome(
            id=question.id,
            ok=ok,
            summary=f"jev:{question.id} (noul >= {minimum})",
            detail={**detail, "min": minimum, "ok": ok},
            error="" if ok else f"noul {noul} < min {minimum}",
        )

    if question.type == "choice":
        chosen = answer.get("choice")
        expected = question.expected
        if not isinstance(chosen, str) or expected is None:
            return JevQuestionOutcome(
                id=question.id,
                ok=False,
                summary=f"jev:{question.id} (choice == {expected})",
                detail=detail,
                error="choice answer missing or expected value unset",
            )
        ok = chosen == expected
        return JevQuestionOutcome(
            id=question.id,
            ok=ok,
            summary=f"jev:{question.id} (choice == {expected})",
            detail={**detail, "expected": expected, "ok": ok},
            error="" if ok else f"choice {chosen!r} != expected {expected!r}",
        )

    if question.type == "score":
        score = _as_float(answer.get("score"))
        minimum = question.min_value
        if score is None or minimum is None:
            return JevQuestionOutcome(
                id=question.id,
                ok=False,
                summary=f"jev:{question.id} (score >= {minimum})",
                detail=detail,
                error="score answer was not a number or min is unset",
            )
        ok = score >= minimum
        return JevQuestionOutcome(
            id=question.id,
            ok=ok,
            summary=f"jev:{question.id} (score >= {minimum})",
            detail={**detail, "min": minimum, "ok": ok},
            error="" if ok else f"score {score} < min {minimum}",
        )

    return JevQuestionOutcome(
        id=question.id,
        ok=False,
        summary=f"jev:{question.id}",
        detail=detail,
        error=f"unsupported question type {question.type!r}",
    )


def evaluate_response(config: JevConfig, payload: dict) -> JevEvaluation:
    answers = payload.get("answers")
    public = public_answers(answers)
    usage = public_usage(payload.get("usage"))
    model = payload.get("model")
    model_text = str(model).strip() if model is not None else None
    if not isinstance(answers, dict):
        return JevEvaluation(
            ok=False,
            model=model_text or config.model,
            usage=usage,
            answers=public,
            transport_error="Jev response JSON has no answers object",
        )
    outcomes = [
        evaluate_question(question, answers.get(question.id)) for question in config.questions
    ]
    return JevEvaluation(
        ok=all(outcome.ok for outcome in outcomes),
        model=model_text or config.model,
        usage=usage,
        answers=public,
        outcomes=outcomes,
    )


def run_jev(
    goal: Goal,
    *,
    timeout: int,
    env: dict[str, str],
    request: SystemoneRequest | None = None,
) -> JevEvaluation:
    config = goal.jev
    if config is None:
        return JevEvaluation(
            ok=False,
            transport_error="verifier_backend is jev but GOAL.md has no jev: block",
        )
    api_key = (env.get(API_KEY_ENV) or "").strip()
    if not api_key:
        return JevEvaluation(
            ok=False,
            model=config.model,
            transport_error=(
                f"{API_KEY_ENV} is not set. Jev verifier is fail-closed "
                "(export your own TypeSafe key; this repo never ships one)."
            ),
        )

    post = request or systemone_request
    payload = config.api_payload()
    try:
        status, body = post(payload, api_key, timeout)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        return JevEvaluation(
            ok=False,
            model=config.model,
            transport_error=redact_secrets(
                f"Jev request failed: {exc}",
                api_key,
            ),
        )

    body = redact_secrets(body, api_key)
    if status != 200:
        snippet = body.strip() or "(empty body)"
        return JevEvaluation(
            ok=False,
            model=config.model,
            transport_error=f"Jev HTTP {status}: {snippet}",
        )
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        return JevEvaluation(
            ok=False,
            model=config.model,
            transport_error=f"Jev response JSON could not be parsed: {exc}",
        )
    if not isinstance(parsed, dict):
        return JevEvaluation(
            ok=False,
            model=config.model,
            transport_error="Jev response JSON must be an object",
        )
    return evaluate_response(config, parsed)
