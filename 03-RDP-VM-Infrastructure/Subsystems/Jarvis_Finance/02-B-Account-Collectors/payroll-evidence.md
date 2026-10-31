# Payroll Evidence — Regions, SoFi, and Gusto

**Evidence basis:** Collector B closeout, October 29, 2026.

## Cash received versus gross earned

These are separate facts and must remain separate:

- **Cash received:** confirmed posted payroll deposits in Regions or SoFi, supported by the original bank transaction, posting date, account provenance, and descriptor.
- **Gross earnings:** an authentic payroll record, employer pay statement, offer letter, or other identified primary payroll source.
- **Unknown gross:** if no reliable gross source exists, preserve `gross_pay_status = UNKNOWN`. Net deposits are not gross wages.

A projection may use a clearly labeled estimate with its assumptions and provenance. It must never be stored as an observed payroll fact.

## Matching contract

A paycheck-to-deposit match should consider:

- Posting date and payroll period
- Amount and split-deposit pattern
- Employer or payroll descriptor
- Posted / pending status
- Account provenance
- Evidence that the same economic event has not already been represented by another connected source

Use explicit outcomes such as `MATCHED`, `CANDIDATE`, and `UNMATCHED`. Do not assign a blanket 95% confidence score without a measured method.

## Gusto scope

| Stage | Purpose | Status |
|---|---|---|
| Stage 1 | Time-clock / dispatcher agent | Existing service was reported running; preserve it unchanged |
| Stage 2 | Browser-based payroll PDF retrieval | Optional and deferred |

The Collector B closeout deliberately stops further Stage 2 Chromium/CDP troubleshooting. No verified paystub PDF or paycheck-to-bank match was accepted, and no Stage 2 timer was installed by that closeout.

## Do not do

- Do not treat every bank credit as payroll.
- Do not count transfers among owned accounts as income.
- Do not treat a Stage 1 dispatcher cycle as proof of paystub retrieval.
- Do not derive gross wages from net deposits.
- Do not upload paystub PDFs, cookies, or detailed payroll exports to this public repository.

## Finance Master dependency

Finance Master must verify posted deposit feeds, source freshness, transfer de-duplication, and the mapping of split payroll deposits before using B data for canonical income reporting.
