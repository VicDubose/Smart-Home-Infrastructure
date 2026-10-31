# F — Finance Command Center and Home Assistant

**Maps to parent README:** Section 12

## Purpose

F is the read-only presentation layer for accepted Finance evidence. The interface is deployed and its four views were visually verified. Current financial snapshot integration is a separate, still-pending acceptance gate.

## Four dashboard views

| View | Purpose | Data acceptance boundary |
|---|---|---|
| Finance Chief | Trusted analysis and review-only advisory | No accepted current Chief feed established |
| Market Watch | Public snapshots, filings, source dates, review states | D source-to-dashboard mapping not accepted |
| Cash Flow & Debt | Inflows, spending, reserves, debt with as-of dates | Current B/C snapshot not accepted |
| Strategy Lab | Deterministic scenarios and allocation comparisons | Live validated scenario engine not accepted |

## Deployment and publication contract

- Existing service: `jarvis-finance-command-center.service`
- Dashboard schema: `jarvis.finance.dashboard_snapshot_v0_1`
- Intended source: an accepted, trusted snapshot publisher consuming validated C/D outputs and optional separately accepted E outputs.
- Required metadata: source as-of dates, observation times, coverage, reconciliation, lineage, last-good state, staleness, and advisory clearance.
- Page refresh must only read the saved snapshot. It must not start bank sync, market collection, model inference, scheduler changes, or financial transactions.

## Dashboard image

The screenshot is stored in the sibling `Screenshots` folder. Review it for private balances, names, account identities, internal addresses, hostnames, and tokens before publishing.

![JARVIS Finance Command Center](../Screenshots/JARVIS%20Finance%20Command%20Center%20Dashboard%20%281%29.png)

*JARVIS Finance Command Center — dashboard overview.*

## Home Assistant

Home Assistant embeds the Finance Command Center as iframe views. The HA view is a presentation surface; it does not own financial collection, reconciliation, or AI reasoning.

See [dashboard and HA details](dashboard-and-ha.md) and the [parent F section](../README.md#12-f--finance-command-center-and-home-assistant).
