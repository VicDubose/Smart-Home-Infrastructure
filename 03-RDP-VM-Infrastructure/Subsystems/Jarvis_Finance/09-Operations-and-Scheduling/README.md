# Operations, Scheduling, and Recovery

**Maps to parent README:** Sections 14, 15, and 17

## Purpose

This folder documents when Finance collection is intended to run, who owns each schedule, how failures are contained, and which signals prove that unattended operation actually occurred.

## Scheduling principles

- Use `America/Chicago` consistently.
- Preserve Tuesday as a discretionary JARVIS rest day.
- Keep weekends for separately inventoried heavy work.
- Prefer the central JARVIS scheduler when it owns the job.
- Never install a second timer before checking the scheduler and existing units.
- A schedule proposal or installed timer is not proof of a successful unattended run.

## Known source-specific status

| Workload | Desired cadence | Handoff status |
|---|---|---|
| Actual / Simply Budget | Daily; commissioning kit proposes 06:40 | Timer installer defaults disabled; enablement and unattended success require host evidence |
| Regions / SoFi | Refresh suitable for posted-deposit reporting | Freshness and full coverage require proof |
| Nelnet | Monthly | Authenticated monthly acquisition and timer not demonstrated |
| Market Watch D | User-approved M/W/F and Thu windows, source-aware | v1.8.1 release prepared; activation and unattended receipts not verified in handoff |
| Gusto Stage 2 | Optional | Deferred; no timer required |
| Dashboard | Read saved snapshot | No collection or inference on page refresh |

## Detailed pages

- [Schedule ownership and cadence](scheduling.md)
- [Failure recovery and observability](recovery-and-observability.md)
