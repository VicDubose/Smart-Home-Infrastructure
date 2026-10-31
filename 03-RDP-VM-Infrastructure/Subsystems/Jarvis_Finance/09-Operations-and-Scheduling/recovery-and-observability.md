# Failure Recovery and Operational Observability

## Fail-closed recovery

A failed or ambiguous refresh must not overwrite a previous accepted snapshot or relabel old evidence as current.

Expected behavior:
1. Preserve the last-good immutable snapshot and its original as-of date.
2. Write a failure or degraded receipt.
3. Mark the affected source stale, unavailable, unknown, or conflicted.
4. Do not publish partial data as complete.
5. Retry only when the source operation is known to be safe and idempotent.
6. Confirm that replay does not create duplicate events or alerts.

## Required operational signals

| Signal | Why it matters |
|---|---|
| Last attempt and last successful run | A running service can still fail to produce accepted evidence |
| Source as-of and observed-at | Collection time does not refresh an old source fact |
| Account / source coverage | Shows which providers and periods were included |
| Reconciliation state | Exposes duplicate income, transfers, or loan-family gaps |
| Quarantine count and reason | Makes unresolved source ambiguity visible |
| Last-good hash and age | Supports safe recovery |
| Timer, lock, and receipt state | Demonstrates real unattended operation |
| Contract, policy, and model versions | Supports reproducibility |
| Dashboard snapshot status | A healthy UI may still show stale or absent data |

## Acceptance tests

- [ ] Force a source timeout and verify last-good remains unchanged.
- [ ] Repeat a successful source run and verify idempotency.
- [ ] Test missing account coverage and stale source timestamps.
- [ ] Restart services and verify prohibited model/source jobs do not start unexpectedly.
- [ ] Verify dashboard labels accurately distinguish current, historical, stale, unknown, and unavailable evidence.
