# Timer Inventory

| Timer | Schedule |
|---|---|
| `caleb-edge-guard.timer` | every 5 minutes |
| `caleb-edge-health.timer` | daily 06:00, randomized delay up to 10m |
| `caleb-edge-maintenance.timer` | 1st and 15th at 03:30, randomized delay up to 15m |
| `caleb-staging-flush.timer` | hourly, randomized delay up to 5m |
| `caleb-local-events-overnight.timer` | Sun/Wed 01:00 |
| `caleb-local-events-morning-release.timer` | Sun/Wed 06:00 |
| `caleb-local-events-expiry-cleanup.timer` | daily 22:00 |

## Legacy — do not enable

- `jarvis-vpn-start.timer`: old Friday 01:00 policy — disabled.
- `jarvis-vpn-stop.timer`: old Friday 10:00 policy — disabled.
