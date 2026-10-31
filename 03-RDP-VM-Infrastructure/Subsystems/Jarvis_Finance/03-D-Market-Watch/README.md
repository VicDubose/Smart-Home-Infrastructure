# D — Market Watch and Public-Data Acquisition

**Maps to parent README:** Section 6
**Evidence basis:** Market Watch D handoff v1.8.1 and commissioning audit v1.6, evidence through October 29–30, 2026.

## Purpose

D collects public-market disclosures and reference data for Finance Master. It is a public-data observation lane, not a personal portfolio ledger, investment adviser, or trading service.

## Source coverage

- Public M1 Dividend and Growth pie targets
- SEC Form 4 filings for selected public-company insiders
- SEC Form 13F institutional holdings disclosures
- ARKK official fund holdings
- FRED S&P 500 and Nasdaq-100 price indexes
- U.S. Treasury par-yield curve
- FDIC national CD average/reference rates

## Evidence-backed status

Historical source collection and several validation packages passed. The October 29 handoff still classified unattended scheduling, dashboard freshness delivery, and final closeout as unverified. The v1.8.1 timer wrapper had local tests, but server activation and unattended execution were not established by that handoff.

## Critical interpretation rules

- M1 pies are public target allocations, not authenticated current holdings or trades.
- ARKK holdings are ETF holdings, not Cathie Wood's private portfolio.
- 13F filings are delayed institutional disclosures, not contemporaneous trade records.
- Form 4 rows require accession, amendment, and transaction-code context.
- FRED index observations are price-only, not total-return series.
- Treasury par yields are reference yields, not executable bond quotes or realized returns.
- FDIC national CD averages are reference averages, not an available bank's quoted APY.

## Detailed pages

- [Source catalog and interpretation](source-catalog.md)
- [Schedule, commissioning, and acceptance](schedule-and-acceptance.md)

## Authority boundary

D may collect, normalize, preserve, and qualify public observations. It has no authority to trade, change personal accounts, infer private holdings, or enable AI investment execution.
