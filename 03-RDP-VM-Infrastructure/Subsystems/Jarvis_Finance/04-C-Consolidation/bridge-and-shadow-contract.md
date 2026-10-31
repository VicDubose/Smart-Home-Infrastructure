# C — Bridge and Shadow Contract

## Source-derived behavior

The October 30 handoff describes these boundaries:

1. The Actual bridge v0.2 normalizes private getter snapshots.
2. It verifies transfer-link reciprocity.
3. It does not independently prove live bank synchronization or posting freshness.
4. Unverified account aliases and currency mappings remain unresolved.
5. It does not yet reconcile the economic meaning of payroll deposits.
6. Contract shadow v0.3 emits a SHA-pinned, JSON-Schema-validated private event stream.
7. A shadow event stream is not a production C publication.

The Nelnet validator reads checked page text already collected by the Account Evidence Collector. It validates the expected twelve groups, duplicate-field consensus, and principal/interest/outstanding arithmetic. It is not an acquisition worker.

## Shadow-stage safety

The documented `--stage-shadow` process requires a matching accepted B receipt and private snapshot. It checks source count and collection timestamps, reuses the existing bridge, checks transfer consistency, and verifies the contract's source hash.

It does not:
- Log in to a bank or Nelnet
- Download a new statement
- Start or enable a timer
- Change accounts
- Publish to the Finance Dashboard
- Grant Finance Chief or trading authority

## Promotion gates

- [ ] Accepted B source receipt and scope
- [ ] Verified upstream freshness and account mapping
- [ ] Currency and monetary-unit validation
- [ ] Owned-account transfer de-duplication
- [ ] Split-payroll economic-event reconciliation
- [ ] Loan-group and balance reconciliation
- [ ] Schema, hash, and provenance validation
- [ ] Adverse-case tests and idempotent replay
- [ ] Separate Finance Master approval before production publication

Keep all real event payloads and financial values private.
