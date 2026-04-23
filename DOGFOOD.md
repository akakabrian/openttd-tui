# DOGFOOD — openttd

_Session: 2026-04-23T13:23:26, driver: pty, duration: 3.0 min_

**PASS** — ran for 1.9m, captured 12 snap(s), 1 milestone(s), 0 blocker(s), 0 major(s).

## Summary

Ran a rule-based exploratory session via `pty` driver. Found no findings worth flagging. Game reached 61 unique state snapshots. Captured 1 milestone shot(s); top candidates promoted to `screenshots/candidates/`. 1 coverage note(s) — see Coverage section.

## Findings

### Blockers

_None._

### Majors

_None._

### Minors

_None._

### Nits

_None._

### UX (feel-better-ifs)

_None._

## Coverage

- Driver backend: `pty`
- Keys pressed: 965 (unique: 46)
- State samples: 76 (unique: 61)
- Score samples: 0
- Milestones captured: 1
- Phase durations (s): A=82.0, B=16.1, C=18.0
- Snapshots: `/home/brian/AI/projects/tui-dogfood/reports/snaps/openttd-20260423-132128`

Unique keys exercised: -, /, 2, 3, 5, :, ;, ?, H, R, ], b, backspace, c, ctrl+l, d, delete, down, enter, escape, f, f1, f2, h, home, k, l, left, m, n, p, page_down, q, question_mark, r, right, s, shift+slash, shift+tab, space ...

### Coverage notes

- **[CN1] Phase B exited early due to saturation**
  - State hash unchanged for 10 consecutive samples during the stress probe; remaining keys skipped.

## Milestones

| Event | t (s) | Interest | File | Note |
|---|---|---|---|---|
| first_input | 0.3 | 0.0 | `openttd-20260423-132128/milestones/first_input.txt` | key=up |
