---
status: active
slug: frontmatter-schema
objective: Parse checklist, non_goals, and progress from YAML as well as the body.
verifier: python -c "raise SystemExit(0)"
checklist:
  - "[ ] body-style unchecked"
  - "[x] body-style checked"
  - plain item defaults to open
non_goals:
  - SaaS
  - star fraud
progress:
  - date: 2026-09-19
    note: yaml progress row
  - "2026-09-18: string progress row"
---

# frontmatter-schema

This file has a required body. Structured fields live in the frontmatter.
