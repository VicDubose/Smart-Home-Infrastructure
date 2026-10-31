# B — Financial Account Collectors

**Maps to parent README:** Section 5
**Evidence basis:** Collector B closeout dated October 29, 2026, and Actual daily commissioning package dated October 30, 2026.

## Purpose

Workstream B acquires private financial evidence from linked accounts, the Actual / Simply Budget ledger, payroll-related sources, and debt providers. It records what a source actually returned, when it was observed, and what scope was covered.

B is an evidence collector. It does not decide how money should be allocated, publish a canonical financial state, or authorize financial actions.

## Component map

| Component | Role | Evidence-backed state |
|---|---|---|
| Regions / SoFi | Posted deposit and account evidence | Intended primary cash-received evidence; recurring freshness and full coverage still require proof |
| Actual / Simply Budget | Ledger, transaction, category, and account extraction | Existing getter pilot ran twice; daily bank-sync commissioning package prepared; unattended acceptance not established by the handoff |
| Gusto Stage 1 | Time-clock / dispatcher workflow | Existing agent and dispatcher timer were reported running |
| Gusto Stage 2 | Optional paystub PDF capture | Deferred; no accepted PDF or deposit match |
| Nelnet | Student-loan evidence validation | Validator exists; monthly authenticated acquisition and timer not demonstrated |

## Important reporting rules

- Count income received from verified posted deposits, not every credit or aggregator duplicate.
- Exclude transfers between accounts owned by the user from income totals.
- Distinguish net cash received from gross earnings.
- If no authentic gross-pay source is available, report gross as `UNKNOWN`; do not infer it from net deposits.
- Mark unmatched or ambiguous credits as candidates or unknowns rather than assigning an unsupported confidence percentage.
- Keep raw bank records, paystubs, loan statements, credentials, and detailed receipts in private storage.

## Detailed pages

- [Actual daily collection](actual-daily.md)
- [Payroll and Gusto evidence](payroll-evidence.md)
- [Nelnet evidence and limits](nelnet.md)

## Current acceptance boundary

B is not accepted end-to-end merely because a container, getter, validator, or dashboard is running. Acceptance requires source freshness, complete account scope, real receipts, correct transfer and income classification, and source-specific recurring execution.

See the [parent Collector B section](../README.md#5-b--financial-account-collectors).
