# C — Consolidation and Canonical Financial State

**Maps to parent README:** Section 7
**Evidence basis:** B→C shadow handoff and Nelnet validator package, October 30, 2026.

## Purpose

C transforms accepted source observations into a private, reconciled financial state. It is the point where duplicate representations, owned-account transfers, split payroll, monetary units, source coverage, and conflicts must be resolved.

C must not convert an unverified source into a verified fact or turn a private shadow stream into production publication without separate approval.

## Components documented in the handoff

| Component | Responsibility | Current boundary |
|---|---|---|
| Actual bridge v0.2 | Normalize Actual getter snapshots and check transfer-link reciprocity | Account aliases and currency remain unverified; economic payroll reconciliation and bank posting freshness are not established |
| Contract shadow v0.3 | SHA-pinned, JSON-Schema-validated private event stream | Shadow only; not production C publication |
| Nelnet validator v0.5 | Validate collected loan-group page text and arithmetic | Does not acquire new monthly Nelnet evidence |
| Monetary-units correction v0.3.3 | Explicit units handling in the shadow path | Must be validated with accepted inputs before downstream use |

## C's required outputs

- Canonical economic events with source lineage
- Corrected currency and unit interpretation
- Transfer links and duplicate suppression
- Payroll split-deposit grouping without double-counting
- Account and loan coverage metadata
- Source as-of and observation timestamps
- Reconciliation and conflict state
- A private, schema-valid snapshot candidate

## Current status

The October 30 handoff describes a private shadow path, not an accepted production canonical state. The bridge does not independently prove upstream bank freshness, and the C contract does not authorize dashboard publication.

See [bridge and shadow contract](bridge-and-shadow-contract.md) and the [parent C section](../README.md#7-c--consolidation-and-canonical-financial-state).
