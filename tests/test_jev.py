from __future__ import annotations

import hashlib
import json
import re
import urllib.error
from pathlib import Path

import pytest

from goal_run.errors import GoalParseError
from goal_run.jev import (
    API_KEY_ENV,
    SYSTEMONE_URL,
    evaluate_question,
    evaluate_response,
    public_usage,
    redact_secrets,
    systemone_request,
)
from goal_run.models import DEFAULT_NOUL_MIN, JevQuestion, VerifierBackend
from goal_run.parse import load_goal, parse_goal_text
from goal_run.verify import (
    JSON_CHECK_KEYS,
    JSON_REPORT_KEYS,
    Evidence,
    command_to_check,
    evidence_path,
    json_report,
    run_verifiers,
    verifier_fingerprint,
)
from tests.support import FIXTURES, copy_fixture, invoke, output_of

ROOT = Path(__file__).resolve().parents[1]
SECRET = "dummy-typesafe-key"
REAL_SYSTEMONE_REQUEST = systemone_request

GREEN_RESPONSE = {
    "model": "jev-1.13.0",
    "answers": {
        "is_demo": {"type": "noul", "noul": 0.97},
        "kind": {
            "type": "choice",
            "choice": "demo",
            "confidence": 0.9,
            "probabilities": {"demo": 0.95, "production": 0.05},
        },
        "clarity": {
            "type": "score",
            "score": 2.0,
            "confidence": 0.9,
            "legend": {
                "0": "Not at all",
                "1": "Somewhat",
                "2": "Explicitly a demonstration",
            },
            "probabilities": {"0": 0.0, "1": 0.0, "2": 1.0},
        },
    },
    "usage": {
        "input_tokens": 120,
        "output_tokens": 20,
        "cost_usd": 0.00001,
        "credits_remaining_usd": 4.99,
    },
}


def _jev_goal(
    extra_questions: str = "",
    *,
    backend: str = "jev",
    verifier: str | None = None,
    model: str = "jev-latest",
) -> str:
    questions = """
    is_demo:
      type: noul
      instructions: The state describes a canned demonstration.
      min: 0.8
"""
    questions += extra_questions
    verifier_block = f"verifier:\n  - {verifier}\n" if verifier else ""
    backend_block = f"verifier_backend: {backend}\n" if backend else ""
    return f"""---
status: active
slug: jev-test
objective: Optional Jev unit test goal.
{backend_block}{verifier_block}jev:
  model: {model}
  state: This is a canned demonstration state, not a live incident.
  questions:
{questions}
---

## Checklist

- [x] One
"""


@pytest.fixture(autouse=True)
def _no_live_typesafe(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)

    def _blocked(*args, **kwargs):
        raise AssertionError("live TypeSafe HTTP is not allowed in tests")

    monkeypatch.setattr("goal_run.jev.systemone_request", _blocked)


def _write_goal(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "GOAL.md"
    path.write_text(text, encoding="utf-8")
    return path


def _fake_response(payload: dict, status: int = 200):
    def _request(body: dict, api_key: str, timeout: int):
        _request.calls.append({"body": body, "api_key": api_key, "timeout": timeout})
        if status != 200:
            return status, json.dumps(payload)
        return 200, json.dumps(payload)

    _request.calls = []
    return _request


def test_shell_fingerprint_matches_v011_algorithm():
    goal = load_goal(FIXTURES / "check_pass.md")
    expected = hashlib.sha256(
        "\n".join(cmd.strip() for cmd in goal.verifiers).encode("utf-8")
    ).hexdigest()
    assert verifier_fingerprint(goal) == expected
    assert goal.verifier_backend is VerifierBackend.SHELL


def test_shell_evidence_omits_jev_keys(tmp_path):
    goal = copy_fixture(tmp_path, "check_pass.md")
    parsed = load_goal(goal)
    evidence = run_verifiers(parsed)
    raw = json.loads(evidence.to_json())
    assert evidence.ok
    assert "backend" not in raw
    assert "model" not in raw
    assert "usage" not in raw
    assert "answers" not in raw
    assert "commands" in raw


def test_boolean_type_rejected():
    text = _jev_goal(
        """
    bad:
      type: boolean
      instructions: Is this done?
"""
    )
    with pytest.raises(GoalParseError, match="noul"):
        parse_goal_text(text)


def test_jev_without_backend_and_without_shell_is_parse_error():
    text = _jev_goal(backend="")
    with pytest.raises(GoalParseError, match="verifier_backend"):
        parse_goal_text(text)


def test_jev_backend_without_block_is_parse_error():
    text = """---
status: active
slug: missing-jev
objective: Flag without config.
verifier_backend: jev
---

## Checklist

- [ ] a
"""
    with pytest.raises(GoalParseError, match="no jev"):
        parse_goal_text(text)


def test_choice_requires_expected_and_criteria():
    text = _jev_goal(
        """
    verdict:
      type: choice
      instructions: Pick
      criteria:
        pass: ok
        fail: no
"""
    )
    with pytest.raises(GoalParseError, match="expected"):
        parse_goal_text(text)


def test_noul_default_min_and_yaml_bool_criteria():
    text = """---
status: active
slug: noul-criteria
objective: YAML true/false criteria keys.
verifier_backend: jev
jev:
  state: canned demo
  questions:
    is_demo:
      type: noul
      instructions: Demo?
      criteria:
        true: It is a demo
        false: It is not a demo
---

## Checklist

- [ ] a
"""
    goal = parse_goal_text(text)
    question = goal.jev.questions[0]
    assert question.min_value == DEFAULT_NOUL_MIN
    assert question.criteria == {"true": "It is a demo", "false": "It is not a demo"}


def test_jev_block_ignored_when_shell_backend(tmp_path):
    text = _jev_goal(backend="shell", verifier='python -c "raise SystemExit(0)"')
    path = _write_goal(tmp_path, text)
    goal = load_goal(path)
    assert goal.verifier_backend is VerifierBackend.SHELL
    evidence = run_verifiers(goal)
    assert evidence.ok
    assert evidence.backend == VerifierBackend.SHELL.value
    assert evidence.commands[0].cmd.startswith("python")


def test_missing_key_is_red_without_http(tmp_path):
    path = _write_goal(tmp_path, _jev_goal())
    goal = load_goal(path)
    evidence = run_verifiers(goal)
    assert evidence.ok is False
    combined = evidence.to_json()
    assert "TYPESAFE_API_KEY" in combined
    assert "fail-closed" in combined
    assert SECRET not in combined


def test_thresholds_not_sent_and_green_evidence_has_no_secret(tmp_path, monkeypatch):
    fake = _fake_response(GREEN_RESPONSE)
    monkeypatch.setattr("goal_run.jev.systemone_request", fake)
    path = _write_goal(tmp_path, (ROOT / "examples" / "jev.md").read_text(encoding="utf-8"))
    goal = load_goal(path)
    evidence = run_verifiers(goal, env={"TYPESAFE_API_KEY": SECRET})
    assert evidence.ok, [row.stderr for row in evidence.commands]
    assert fake.calls, "expected a mocked HTTP call"
    sent = fake.calls[0]["body"]

    def _no_threshold_keys(obj: object) -> None:
        if isinstance(obj, dict):
            assert "min" not in obj
            assert "expected" not in obj
            for value in obj.values():
                _no_threshold_keys(value)
        elif isinstance(obj, list):
            for value in obj:
                _no_threshold_keys(value)

    _no_threshold_keys(sent)
    assert sent["questions"]["is_demo"]["type"] == "noul"
    assert sent["model"] == "jev-latest"
    raw = evidence.to_json()
    assert SECRET not in raw
    assert "Bearer" not in raw
    assert evidence.backend == "jev"
    assert evidence.model == "jev-1.13.0"
    assert evidence.usage == {
        "input_tokens": 120,
        "output_tokens": 20,
        "cost_usd": 0.00001,
    }
    assert "credits_remaining_usd" not in json.dumps(evidence.usage)
    assert evidence.answers["kind"]["choice"] == "demo"
    assert evidence.answers["is_demo"]["noul"] == 0.97


def test_noul_below_threshold_is_red():
    question = JevQuestion(
        id="done",
        type="noul",
        instructions="Done?",
        min_value=0.8,
    )
    outcome = evaluate_question(question, {"type": "noul", "noul": 0.2})
    assert outcome.ok is False


def test_choice_mismatch_is_red():
    question = JevQuestion(
        id="kind",
        type="choice",
        instructions="Kind?",
        criteria={"demo": "d", "prod": "p"},
        expected="demo",
    )
    outcome = evaluate_question(question, {"type": "choice", "choice": "prod"})
    assert outcome.ok is False


def test_score_pass_and_fail():
    question = JevQuestion(
        id="quality",
        type="score",
        instructions="Quality?",
        criteria=["a", "b", "c"],
        min_value=1.5,
    )
    assert evaluate_question(question, {"type": "score", "score": 2.0}).ok is True
    assert evaluate_question(question, {"type": "score", "score": 0.4}).ok is False


def test_http_401_is_red(tmp_path, monkeypatch):
    fake = _fake_response({"detail": "authentication_error"}, status=401)
    monkeypatch.setattr("goal_run.jev.systemone_request", fake)
    goal = load_goal(_write_goal(tmp_path, _jev_goal()))
    evidence = run_verifiers(goal, env={"TYPESAFE_API_KEY": SECRET})
    assert evidence.ok is False
    assert "401" in evidence.commands[0].stderr
    assert SECRET not in evidence.to_json()


def test_malformed_json_is_red(tmp_path, monkeypatch):
    def fake(payload, api_key, timeout):
        return 200, "not-json{"

    monkeypatch.setattr("goal_run.jev.systemone_request", fake)
    goal = load_goal(_write_goal(tmp_path, _jev_goal()))
    evidence = run_verifiers(goal, env={"TYPESAFE_API_KEY": SECRET})
    assert evidence.ok is False
    assert "JSON" in evidence.commands[0].stderr


def test_missing_answers_is_red(tmp_path, monkeypatch):
    fake = _fake_response({"model": "jev-1.13.0"})
    monkeypatch.setattr("goal_run.jev.systemone_request", fake)
    goal = load_goal(_write_goal(tmp_path, _jev_goal()))
    evidence = run_verifiers(goal, env={"TYPESAFE_API_KEY": SECRET})
    assert evidence.ok is False
    assert "answers" in evidence.commands[0].stderr.lower()


def test_transport_error_is_red(tmp_path, monkeypatch):
    def fake(payload, api_key, timeout):
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr("goal_run.jev.systemone_request", fake)
    goal = load_goal(_write_goal(tmp_path, _jev_goal()))
    evidence = run_verifiers(goal, env={"TYPESAFE_API_KEY": SECRET})
    assert evidence.ok is False
    assert "timed out" in evidence.commands[0].stderr


def test_fingerprint_changes_when_threshold_changes():
    low = parse_goal_text(_jev_goal())
    high = parse_goal_text(_jev_goal().replace("min: 0.8", "min: 0.99"))
    assert verifier_fingerprint(low) != verifier_fingerprint(high)


def test_redact_secrets():
    text = "Authorization: Bearer " + SECRET + "\n" + API_KEY_ENV + "=" + SECRET + "\n"
    out = redact_secrets(text, SECRET)
    assert SECRET not in out
    assert "[redacted]" in out


def test_public_usage_drops_balance():
    assert public_usage(GREEN_RESPONSE["usage"]) == {
        "input_tokens": 120,
        "output_tokens": 20,
        "cost_usd": 0.00001,
    }


def test_evaluate_response_mixed_fail():
    config = parse_goal_text(_jev_goal()).jev
    payload = {
        "model": "jev-1.13.0",
        "answers": {"is_demo": {"type": "noul", "noul": 0.1}},
    }
    result = evaluate_response(config, payload)
    assert result.ok is False


def test_check_cli_jev_green(monkeypatch, runner, tmp_path):
    fake = _fake_response(GREEN_RESPONSE)
    monkeypatch.setattr("goal_run.jev.systemone_request", fake)
    monkeypatch.setenv("TYPESAFE_API_KEY", SECRET)
    dest = tmp_path / "GOAL.md"
    dest.write_text((ROOT / "examples" / "jev.md").read_text(encoding="utf-8"), encoding="utf-8")
    result = invoke(runner, "check", "--goal", str(dest))
    assert result.exit_code == 0, result.output
    assert "GREEN" in result.output
    stored = json.loads(evidence_path(dest).read_text(encoding="utf-8"))
    assert stored["ok"] is True
    assert stored["backend"] == "jev"
    assert stored["model"] == "jev-1.13.0"
    blob = json.dumps(stored)
    assert SECRET not in blob
    assert "credits_remaining_usd" not in blob
    evidence = Evidence.from_dict(stored)
    report = json_report(
        ok=evidence.ok,
        exit_code=0,
        checks=[command_to_check(row) for row in evidence.commands],
        evidence=evidence_path(dest),
    )
    assert tuple(report) == JSON_REPORT_KEYS
    assert report["checks"]
    for row in report["checks"]:
        assert tuple(row) == JSON_CHECK_KEYS


def test_check_cli_jev_missing_key(runner, tmp_path):
    dest = tmp_path / "GOAL.md"
    dest.write_text((ROOT / "examples" / "jev.md").read_text(encoding="utf-8"), encoding="utf-8")
    result = invoke(runner, "check", "--goal", str(dest))
    assert result.exit_code == 1
    assert "RED" in output_of(result)
    stored = json.loads(evidence_path(dest).read_text(encoding="utf-8"))
    assert stored["ok"] is False
    assert "TYPESAFE_API_KEY" in stored["commands"][0]["stderr"]


def test_status_shows_jev_backend(runner, tmp_path):
    dest = tmp_path / "GOAL.md"
    dest.write_text((ROOT / "examples" / "jev.md").read_text(encoding="utf-8"), encoding="utf-8")
    status = invoke(runner, "status", "--goal", str(dest))
    assert status.exit_code == 0
    assert "verifier_backend: jev" in status.output
    assert "is_demo: noul" in status.output


def test_done_archives_jev_when_green(monkeypatch, runner, tmp_path):
    fake = _fake_response(GREEN_RESPONSE)
    monkeypatch.setattr("goal_run.jev.systemone_request", fake)
    monkeypatch.setenv("TYPESAFE_API_KEY", SECRET)
    dest = tmp_path / "GOAL.md"
    text = (ROOT / "examples" / "jev.md").read_text(encoding="utf-8")
    dest.write_text(text.replace("- [ ]", "- [x]"), encoding="utf-8")
    assert invoke(runner, "check", "--goal", str(dest)).exit_code == 0
    result = invoke(runner, "done", "--goal", str(dest), "--date", "2026-09-21")
    assert result.exit_code == 0, result.output
    archived = tmp_path / "goals" / "archive" / "2026-09-21-jev-opt-in-demo.md"
    assert archived.is_file()
    assert not dest.exists()


def test_systemone_request_sends_bearer_via_mocked_opener(monkeypatch):
    captured: dict = {}

    class _Resp:
        status = 200

        def read(self):
            return json.dumps({"model": "jev-1.13.0", "answers": {}}).encode()

        def getcode(self):
            return 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class _Opener:
        def open(self, req, timeout=None):
            captured["url"] = req.full_url
            captured["headers"] = dict(req.header_items())
            captured["auth"] = req.get_header("Authorization")
            captured["timeout"] = timeout
            captured["body"] = req.data
            return _Resp()

    monkeypatch.setattr("goal_run.jev.urllib.request.build_opener", lambda *a, **k: _Opener())
    status, body = REAL_SYSTEMONE_REQUEST(
        {"model": "jev-latest", "state": "x", "questions": {}},
        SECRET,
        7,
    )
    assert status == 200
    assert json.loads(body)["model"] == "jev-1.13.0"
    assert captured["url"] == SYSTEMONE_URL
    assert captured["auth"] == f"Bearer {SECRET}"
    assert captured["timeout"] == 7
    assert SECRET not in body


def test_repo_does_not_ship_typesafe_keys():
    skip_dirs = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache"}
    assigned = re.compile(r"TYPESAFE_API_KEY\s*=\s*['\"]?(\S+)")
    for path in ROOT.rglob("*"):
        if any(part in skip_dirs or part.endswith(".egg-info") for part in path.parts):
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".py", ".yml", ".yaml", ".toml", ".txt", ".json"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in assigned.finditer(text):
            value = match.group(1).strip("'\",")
            if value in {"$TYPESAFE_API_KEY", SECRET, "[redacted]"}:
                continue
            raise AssertionError(f"possible API key assignment in {path}: {match.group(0)}")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "typesafe" not in pyproject.lower()


def test_readme_default_promise_and_opt_in():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "optional" in readme.lower()
    assert "TYPESAFE_API_KEY" in readme
    assert "verifier_backend: jev" in readme
    assert "cost" in readme.lower()
    assert "sk-" not in readme
