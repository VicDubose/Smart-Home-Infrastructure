# Data Provenance and Freshness

## Required fact metadata

A financial or market fact should remain attached to:
- Source identity and content integrity
- Original effective / as-of date
- Observation timestamp
- Fact basis and unit
- Scope coverage
- Reconciliation state
- Confidence or qualification where justified
- Contract and normalization version

## Evidence authority is claim-specific

Examples:
- An authenticated issuer statement is authoritative for its own statement-period balance.
- A posted bank record is authoritative for a specified cash receipt.
- A payroll source record is authoritative for earnings and deductions; the bank posting is authoritative for cash actually received.
- User-approved policy is authoritative for preferences and goals, not current balances or APRs.
- A deterministic calculation inherits the uncertainty and source authority of its inputs.

## Freshness states

| State | Meaning | Required behavior |
|---|---|---|
| `FRESH` | Within the claim's configured window | May proceed to other suitability and policy checks |
| `AGING` | Approaching expiry | Warn and review |
| `STALE` | Outside the window | Retain historical label; do not use as current |
| `UNKNOWN` | Source timing cannot be established | Block affected determinate claims |
| `UNAVAILABLE` | Source absent or collection failed | Retain last-good with old as-of and show missing coverage |
| `CONFLICT` | Material claims disagree | Block dependent decision until reconciled |

The contract's 24-hour ceilings apply to spendable cash and quoted rates. They do not automatically apply to monthly loan statements, quarterly filings, or publication-aware market references.
