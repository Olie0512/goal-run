---
status: active
slug: ship-v0-1-0
objective: Public MVP is installable and independently verifiable. Done when CI is green on this repo and a 총괄 (or other non-implementer) can run the 30s quickstart.
verifier:
  - pytest -q
---

## Checklist

- [x] Ship `goal-run init|status|check|done|archive`
- [x] Parse the GOAL.md schema (status, slug, objective, verifier, checklist, non_goals, progress)
- [x] Refuse `done` unless every box is checked and the last verifier exited 0
- [x] Archive to `goals/archive/YYYY-MM-DD-<slug>.md`
- [x] Fixture tests + CI
- [x] README with a ≤30s red→green path
- [ ] Independent 총괄 verify and `v0.1.0` tag

## Non-goals

- Multi-agent orchestration or a required model inside this CLI
- Cloud sync, auth, dashboards
- Star farming or requiring a paid API for default installs
- A custom marketing landing page

## Progress

- 2026-09-19: CloudAgent implemented the public MVP from SPEC
- 2026-09-21: optional TypeSafe Jev verifier (opt-in, env key only)
