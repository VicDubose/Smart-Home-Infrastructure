# Market Watch D — Schedule and Acceptance

## User-approved lightweight windows

Timezone: `America/Chicago`.

| Day | Proposed Market Watch windows |
|---|---|
| Monday | 08:15, 12:00, 15:45, 21:15 |
| Tuesday | Rest day — no discretionary Market Watch run |
| Wednesday | 08:15, 12:00, 15:45, 21:15 |
| Thursday | 22:00 |
| Friday | 08:15, 12:00, 15:45, 21:15 |
| Saturday / Sunday | Heavy processing only after workload and collision inventory |

The v1.8.1 handoff separates deterministic snapshot-age checks from source refresh. It proposes checks at Monday/Wednesday/Friday 08:15, 12:00, and 15:45, with source refresh at 21:15 and Thursday 22:00. FDIC collection is a source step within the fourth-Thursday refresh rather than a competing timer.

## Commissioning status at the handoff

- v1.8.1 wrapper: 11 local tests passed.
- Five calendar expressions were parsed.
- Timer release was prepared and locally tested.
- Server activation, first scheduled success, and unattended receipts were not verified.
- The v1.6 audit package is read-only; it does not install timers or change policy.
- The canonical source policy was reported as `READ_ONLY_SHADOW`, with automation, AI inference, and investment execution disabled. Any collection-only scheduling exception must be reconciled explicitly with central JARVIS policy.

## Required before activation

- [ ] Inspect the central JARVIS scheduler and all existing jobs.
- [ ] Identify one verified executable entrypoint and runtime per source.
- [ ] Ensure one scheduler owner per collector; no duplicate timers.
- [ ] Preserve AI inference and investment execution as disabled.
- [ ] Apply source-aware cadence, rate limits, Tuesday rest, and weekend collision controls.
- [ ] Prove one unattended run for each scheduled source.
- [ ] Prove timeout/failure behavior preserves last-good data.
- [ ] Verify source as-of dates, quarantine states, and freshness in the dashboard.

Do not blindly run every collector in every window. Cadence must be source-aware and based on actual publication behavior.
