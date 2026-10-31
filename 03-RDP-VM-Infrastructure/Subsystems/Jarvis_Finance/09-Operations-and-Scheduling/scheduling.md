# Scheduling and Job Ownership

## User-approved weekly policy

Timezone: `America/Chicago`.

- Tuesday is a discretionary JARVIS rest day.
- Market Watch lightweight windows: Monday, Wednesday, and Friday at 08:15, 12:00, 15:45, and 21:15; Thursday at 22:00.
- Saturday and Sunday are reserved for major/heavy processing after a collision inventory. Exact weekend jobs and times are not inferred here.

## Actual daily commissioning

The October 30 Actual commissioning kit defines a daily 06:40 timer. Its installer creates the unit disabled by default. A supervised run, explicit enablement, timer-state inspection, and real scheduled receipt are required before calling it unattended.

## Market Watch D

The v1.8.1 handoff separates snapshot-age checks from source refresh. It proposes:
- M/W/F checks at 08:15, 12:00, and 15:45
- M/W/F refresh at 21:15
- Thursday refresh at 22:00
- FDIC as a source step within the fourth-Thursday refresh

The handoff says timer activation and unattended success were not yet verified.

## Scheduler ownership checklist

- [ ] Inventory central JARVIS jobs and systemd timers.
- [ ] Assign one owner per collector.
- [ ] Verify exact executable, environment, and source credentials locally.
- [ ] Confirm source-specific cadence and rate limits.
- [ ] Prevent overlapping runs with a lock.
- [ ] Record job ID/unit, next run, last run, exit status, and receipt.
- [ ] Verify Tuesday and weekend collision policy.
- [ ] Prove failure and recovery behavior.

Do not treat this document as an activation instruction. Use the relevant specialist commissioning handoff and operator approval.
