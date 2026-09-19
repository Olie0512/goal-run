---
status: active
slug: check-fail
objective: Fixture used to prove `goal-run check` goes RED when the verifier exits non-zero.
verifier:
  - python -c "raise SystemExit(2)"
---

## Checklist

- [ ] This box can stay open; check does not require a complete checklist
- [x] Parser still reads mixed boxes

## Non-goals

- Pretending a failing command is green

## Progress

- 2026-09-19: fixture for RED check
