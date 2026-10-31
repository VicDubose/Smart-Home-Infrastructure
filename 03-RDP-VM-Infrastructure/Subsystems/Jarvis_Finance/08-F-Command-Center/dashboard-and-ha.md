# Dashboard and Home Assistant Integration

## Accepted interface scope

The Finance Command Center UI and local Home Assistant iframe deployment were accepted within their interface scope. Historical deployment evidence included 44 Python tests and 7 JavaScript tests.

The four views are:
1. Finance Chief
2. Market Watch
3. Cash Flow & Debt
4. Strategy Lab

## Data publication remains separate

The UI's existence does not prove that its financial values are fresh, complete, or reconciled. The intended private snapshot schema is `jarvis.finance.dashboard_snapshot_v0_1`.

A trusted publisher must validate:
- Schema and contract version
- Source lineage and original as-of dates
- Observation timestamps
- Scope coverage and reconciliation state
- Freshness and degraded/unknown labels
- Last-good versus latest-attempt state
- Any advisory clearance required for Chief content

The page reader should consume the saved snapshot only. No new source collection or model inference should happen on page refresh.

## Home Assistant boundary

HA provides navigation and iframe presentation. It does not become the finance data source, scheduler, or trusted publisher. If the private snapshot is absent or stale, the correct UI behavior is to show empty, historical, or degraded status—not synthetic current balances.

## Screenshot

The dashboard image is stored at `../Screenshots/` relative to this folder. Keep it sanitized before public commit.
