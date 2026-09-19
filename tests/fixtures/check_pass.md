---
status: active
slug: check-pass
objective: Fixture used to prove `goal-run check` goes GREEN when every verifier exits 0.
verifier:
  - python -c "raise SystemExit(0)"
  - python -c "print('second verifier ok')"
---

## Checklist

- [ ] Check may pass while work is still open
- [x] Second item already done

## Non-goals

- Treating GREEN as `done`

## Progress

- 2026-09-19: fixture for GREEN check
