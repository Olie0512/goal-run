---
status: active
slug: demo-red
objective: Demo fixture — `goal-run check` must exit non-zero.
verifier:
  - python -c "raise SystemExit(1)"
---

## Checklist

- [ ] Fix the verifier (or the work it measures)
- [ ] Re-run `goal-run check` until GREEN

## Non-goals

- Editing the evidence file by hand

## Progress

- 2026-09-19: starting RED
