# Finance Decision Contract

## Approved scope

The contract candidate `v1.0.0-rc.1` has design-only approval for isolated implementation and testing. That approval is not production approval and does not authorize financial execution.

## Typed components

| Type | Purpose |
|---|---|
| `FINANCE_INPUT` | Trusted adapter facts, scope, and policy references |
| `MODEL_PROPOSAL` | Bounded candidate, template, or proof selections from a model |
| `FINANCE_OUTPUT` | Trusted deterministic metrics, decisions, and proof certificates |
| `USER_PROFILE` | Versioned intentions and separately labeled user-reported facts |

## Arithmetic and evidence rules

- Money: exact integer cents.
- Rates: typed decimal strings with explicit units.
- Cadence: distinguish weekly, biweekly, semimonthly, monthly, irregular, and unknown.
- Unsupported numbers: preserve null/unknown with a typed reason.
- Every computed result inherits the uncertainty and authority of its source facts.

The approved 24-hour freshness ceilings apply to spendable cash and quoted rates in the contract. They do not automatically apply to monthly loan statements, quarterly filings, or source-specific market references.

## Model restrictions

Fin-R1 and Qwen3 may select from validated candidates and produce bounded synthesis. They must not manufacture source facts, monetary amounts, rates, citations, eligibility, or approval receipts.

Trusted code must validate model output before any advisory is cleared. Missing or unknown central policy clearance means review-only.

## Current acceptance

The contract's design approval and targeted synthetic tests do not establish a general production decision engine. Semantic negatives, independent boundary tests, actual central policy bindings, and full Master acceptance remain mandatory.

**Execution authority:** false.
