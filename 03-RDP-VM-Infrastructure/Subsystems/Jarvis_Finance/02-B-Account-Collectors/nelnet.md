# Nelnet — Evidence Validator and Monthly Acquisition Boundary

**Evidence basis:** B→C shadow handoff, October 30, 2026.

## What the validator does

Nelnet validator v0.5 reads SHA-256-checked `page_text` produced by the existing Account Evidence Collector. It checks:

- The expected twelve loan groups, labeled AA–AL
- Agreement across duplicate fields
- Exact principal, interest, and outstanding-balance arithmetic

It is a validator for already-collected evidence. It is not a Nelnet login client, PDF statement parser, or monthly downloader.

## What remains unproven

The handoff does not demonstrate a monthly live acquisition worker, an active monthly timer, or a fresh monthly receipt. A validator cannot make new source evidence arrive.

Until new authenticated evidence is collected and checked, loan balances must retain a `LAST_VERIFIED_AS_OF` date and must not be presented as current.

## C shadow boundary

The October 30 handoff package can validate and stage a private shadow candidate from an accepted B receipt and a private source snapshot. It does not contact Nelnet, fetch bank data, read the PDF statement, start timers, change accounts, or write to the Finance Dashboard.

## Acceptance required

- [ ] Prove the authenticated monthly source acquisition or an approved statement-import process.
- [ ] Verify the official statement date and expected loan-group set.
- [ ] Run the validator against newly collected source evidence.
- [ ] Preserve group-level discrepancies and source timestamps.
- [ ] Keep any C output private and shadow-only until the Master contract and downstream gates pass.

**Privacy:** Do not publish loan balances, statements, account identifiers, or raw page captures.
