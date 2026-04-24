# DOGFOOD — openttd

_Session: 2026-04-23T14:43:04, driver: pty, duration: 1.5 min_

**PASS** — ran for 1.2m, captured 8 snap(s), 1 milestone(s), 0 blocker(s), 0 major(s).

## Summary

Ran a rule-based exploratory session via `pty` driver. Found no findings worth flagging. Game reached 45 unique state snapshots. Captured 1 milestone shot(s); top candidates promoted to `screenshots/candidates/`.

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
- Keys pressed: 651 (unique: 61)
- State samples: 79 (unique: 45)
- Score samples: 0
- Milestones captured: 1
- Phase durations (s): A=41.0, B=22.5, C=9.0
- Snapshots: `/home/brian/AI/projects/tui-dogfood/reports/snaps/openttd-20260423-144149`

Unique keys exercised: +, ,, -, ., /, 0, 1, 2, 3, 4, 5, :, ;, =, ?, H, R, [, ], a, b, backspace, c, ctrl+l, d, delete, down, end, enter, escape, f, f1, f2, h, home, j, k, l, left, m ...

## Milestones

| Event | t (s) | Interest | File | Note |
|---|---|---|---|---|
| first_input | 0.3 | 0.0 | `openttd-20260423-144149/milestones/first_input.txt` | key=up |
