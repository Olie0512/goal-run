# goal-run

Markdown checklists do not fail. Agents still tick them and say `done`.
This CLI runs the verifier you named: RED (exit 1) or GREEN (exit 0), with the evidence on disk.
`done` refuses a self-grade. That is why you install it instead of another todo list.

**Run until done.** A tiny CLI that turns `GOAL.md` into a state machine with a **separate verifier** — so agents stop declaring victory on vibes.

```bash
pip install -e .                 # or: pip install "git+https://github.com/Olie0512/goal-run"
goal-run init "Ship public MVP"  # writes GOAL.md
# …do the work, tick boxes…
goal-run check                   # RED or GREEN — runs the shell commands you named
goal-run done                    # all boxes + last verifier exit 0 → archive
```

No account, paid API, or model is **required**. Default installs use local shell verifiers only. An optional TypeSafe Jev backend is opt-in (you export your own `TYPESAFE_API_KEY`; this repo never ships one). `python -m goal_run` works the same as `goal-run`.

## Why

Coding agents love opening work and hate finishing it. Loops discover; Goals finish. `goal-run` is the finish primitive: one objective, one checklist, one verifier, then an archive file you can point at.

## Quickstart (≤30s)

Requires Python 3.11+.

```bash
git clone https://github.com/Olie0512/goal-run.git
cd goal-run
# A venv is recommended — and required on some systems (~5s): python3 -m venv .venv && source .venv/bin/activate
pip install -e .
goal-run check --goal tests/fixtures/check_fail.md   # RED  (exit 1)
goal-run check --goal tests/fixtures/check_pass.md   # GREEN (exit 0)
```

That is the whole product: **red → green → (tick every box) → archive**.

`uvx` after a git install:

```bash
uvx --from "git+https://github.com/Olie0512/goal-run" goal-run --help
```

This repo is not published to PyPI yet. Do not `pip install goal-run` from PyPI and expect this project.

## Commands

| Command | What it does |
| --- | --- |
| `goal-run init [objective]` | Scaffold `GOAL.md` + `goals/archive/` |
| `goal-run status` | Parse objective, checklist counts, last evidence |
| `goal-run check [--json]` | Run the verifier (shell commands by default, or optional Jev); write `.goal-run/last-check.json`. `--json` prints `{ok, exit_code, checks, evidence}` on stdout (human text on stderr). RED=1, GREEN=0. |
| `goal-run done` | Archive **only if** every checkbox is ticked **and** the last verifier passed |
| `goal-run archive` | Move a completed (or `--force`) GOAL to `goals/archive/YYYY-MM-DD-<slug>.md` |

`done` refuses a self-grade: ticking boxes is not enough, and a missing verifier is not enough. You must have run `goal-run check` and it must have been GREEN. `done` then re-runs the verifier so the last exit code is fresh.

## GitHub Action

Fails the job when `goal-run check` is RED (exit 1). Pin `@v0.1.2` once that tag exists (or a commit SHA until then).

```yaml
goal:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: Olie0512/goal-run/.github/actions/check@v0.1.2
```

Same check as a reusable workflow: `uses: Olie0512/goal-run/.github/workflows/check.yml@v0.1.2`.

Inputs: `goal` (default `GOAL.md`), `timeout`, `python-version`, `json` (default true → `check --json`). If the GOAL uses Jev, pass `TYPESAFE_API_KEY` as a secret on the step (`env:`); the action does not require it for shell verifiers.

## GOAL.md schema

Frontmatter is optional in the sense that fields can also live under `##` headings. A body is required.

```markdown
---
status: active          # active | blocked | completed
slug: ship-public-mvp
objective: One sentence plus a verifiable done condition.
verifier:
  - pytest -q
---

## Checklist

- [ ] Implement the change
- [ ] Prove it with the verifier

## Non-goals

- Cloud sync
- A required model inside this CLI

## Progress

- 2026-09-19: initialized
```

`verifier` is a shell command or a list of them. They run with `cwd` = the directory that contains `GOAL.md`. Exit 0 is the only green. A command that starts with `python` or `python3` is executed with the same interpreter as `goal-run` (so fixtures work on images that only ship `python3`).

Default backend is `shell`. To opt into TypeSafe Jev instead, see [Optional Jev verifier](#optional-jev-verifier-opt-in).

## Optional Jev verifier (opt-in)

Default `goal-run` stays model-free: no TypeSafe account, no paid API, no extra install. Shell `verifier:` commands are unchanged when you do not set `verifier_backend: jev`.

Jev is a **separate, optional** backend. You bring your own key. The author's key must never appear in this repository, in fixtures, or in docs.

```bash
export TYPESAFE_API_KEY  # your key, from your environment only — never commit it
goal-run check --goal examples/jev.md
```

That example calls `POST https://api.typesafe.ai/v1/systemone` and **costs TypeSafe tokens**. CI in this repo does not make live Jev calls. If the env var is missing, HTTP is not 200, or the response cannot be parsed, `check` is RED (fail-closed).

```markdown
---
status: active
slug: optional-jev
objective: Prove the change with Jev questions against a state you supply.
verifier_backend: jev
jev:
  model: jev-latest          # or pin jev-1.13.0
  state: |
    The artifact under review, as text (or a YAML mapping / list).
  questions:
    done:
      type: noul             # not boolean — noul is calibrated yes/no
      instructions: The work described in the objective is complete.
      min: 0.8               # default 0.8; local threshold, not sent to the API
    verdict:
      type: choice
      instructions: Overall verdict
      criteria:
        pass: Ready to archive
        fail: Not done
      expected: pass
    quality:
      type: score
      instructions: How complete is the implementation?
      criteria:
        - Missing
        - Partial
        - Complete
      min: 2.0
---
```

Pass/fail is local: `noul >= min`, `choice` equals `expected`, `score >= min`. Evidence (`.goal-run/last-check.json`) records the resolved model, usage tokens, and per-question answers/probabilities — never the API key.

No extra pip extra is required (`urllib` is stdlib). There is no `typesafe-sdk` dependency on default installs.

## Red → green → archive

```text
GOAL.md (active)
    │
    ▼
goal-run check ── exit ≠ 0 ──► RED ── fix ──┐
    │                                       │
    └── exit 0 ──► GREEN ◄──────────────────┘
                      │
          all boxes [x] + evidence
                      │
                      ▼
                 goal-run done
                      │
                      ▼
        goals/archive/YYYY-MM-DD-<slug>.md
              (status: completed)
```

```mermaid
flowchart LR
  A[GOAL.md active] --> B["goal-run check"]
  B -->|exit not 0| C[RED]
  C -->|fix the work| B
  B -->|exit 0| D[GREEN]
  D -->|"all [x] + done"| E["goals/archive/YYYY-MM-DD-slug.md"]
```

Try it without touching your own `GOAL.md`:

```bash
# RED
goal-run check --goal tests/fixtures/check_fail.md
# GREEN
goal-run check --goal tests/fixtures/check_pass.md
# refuse (open boxes)
goal-run done --goal tests/fixtures/incomplete.md
```

## Record a GIF / asciinema (optional)

Generating a binary GIF in CI is brittle, so this repo ships a recorder instead of a checked-in movie.

```bash
# once: pip install asciinema   (or brew install asciinema)
./scripts/record-demo.sh
# then, if you want a GIF:
#   agg demo.cast demo.gif     # https://github.com/asciinema/agg
```

See `scripts/record-demo.sh`. Commit `demo.cast` / `demo.gif` only if you generated them locally — they are gitignored by default.

## Principles

- One objective, one checklist, one verifier
- **Verifier ≠ implementer** — `done` refuses a self-grade without passing check evidence
- Archive when complete; never leave a mid-gap `GOAL.md` pretending to be finished

## Non-goals

Not an agent framework. Not a task UI. Not SaaS. Not a star-farming scheme. v1 default installs have no cloud sync, no auth, and no required model. Optional TypeSafe Jev is opt-in only.

## Tests & CI

```bash
pip install -e ".[dev]"
pytest
ruff check src tests
```

CI runs pytest (including parse tests on every fixture `GOAL.md`) and ruff on Ubuntu / Python 3.11 and 3.12.

## License

MIT. See [LICENSE](LICENSE).
