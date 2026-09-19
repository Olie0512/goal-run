---
status: active
slug: demo-green
objective: Demo fixture — `goal-run check` must exit 0. This is not `done`.
verifier:
  - python -c "print('GREEN'); raise SystemExit(0)"
---

## Checklist

- [x] Verifier is a real command
- [ ] Tick this box only when you intend to archive
- [ ] Run `goal-run done` (it will still refuse while a box is open)

## Non-goals

- Calling GREEN the same thing as archived

## Progress

- 2026-09-19: verifier green, checklist still open
