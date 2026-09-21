---
status: active
slug: jev-opt-in-demo
objective: Canned TypeSafe Jev opt-in demo. Done when the named noul/choice/score questions pass local thresholds against this state.
verifier_backend: jev
jev:
  model: jev-latest
  state: |
    This is a canned goal-run demonstration state, not a live scan of any worktree.
    The document under discussion is an example GOAL used only to show optional Jev
    verification. It is explicitly a demo, not a production incident, and not a
    billing or outage report.
  questions:
    is_demo:
      type: noul
      instructions: The state describes a canned demonstration rather than a live production incident.
      min: 0.8
    kind:
      type: choice
      instructions: What kind of document is this state describing?
      criteria:
        demo: A canned example for documentation
        production: A live production goal or incident
      expected: demo
    clarity:
      type: score
      instructions: How clearly does the state identify itself as a demonstration?
      criteria:
        - Not at all
        - Somewhat
        - Explicitly a demonstration
      min: 1.5
---

## Checklist

- [ ] Export your own `TYPESAFE_API_KEY` (this repo never ships a key)
- [ ] Run `goal-run check --goal examples/jev.md` and expect GREEN if Jev agrees
- [ ] Keep default goals on shell verifiers unless you opted in

## Non-goals

- Requiring Jev (or any paid API) for default `goal-run` installs
- Live TypeSafe calls in CI
- Putting an API key in GOAL.md, fixtures, or the README

## Progress

- 2026-09-21: optional Jev verifier example
