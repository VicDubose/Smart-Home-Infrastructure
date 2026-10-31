# Market Watch D — Source Catalog

| Source | What it represents | Qualification |
|---|---|---|
| M1 public pies | Published target weights for public Dividend and Growth pies | Not verified trades, actual holdings, returns, or personal account positions |
| SEC Form 4 | Insider ownership and transaction filings | Retain accession, amendment, and transaction-code context; not every row is an open-market purchase or sale |
| SEC Form 13F | Delayed institutional holdings disclosures | Not real-time trading; amendment and repeated-identity cases require quarantine |
| ARKK official holdings | ETF's published holdings | Not the manager's private portfolio |
| FRED S&P 500 / Nasdaq-100 | Price-index observations | No dividend or total-return inference |
| U.S. Treasury curve | Published par-yield maturities | Reference curve, not executable bond offers or realized returns |
| FDIC national CD reference | Published national CD average terms | Reference averages, not quoted offers from a particular bank |

## Dated evidence recorded in the handoff

- SEC XML exact parity: 22 of 22 files.
- SEC semantic comparison: 12 full-key shadow comparisons; 2 partial ARK comparisons and 3 amendment-blocked pairs remained quarantined.
- SEC change candidates: 1,788 observed in the shadow process; zero published. They are not verified trades.
- FRED: 2,512 aligned common observations through October 28, 2026.
- Treasury: 14 maturities had historical collection-test evidence.
- FDIC: 8 terms had historical collection-test evidence; the reference data's source date remained October 19 in the handoff.
- Form 4: historical evidence covered 6 filings and 33 normalized rows; ongoing accession discovery was not accepted.
- M1: repeated public-pie target validation existed; an unattended recurring browser/session collector was not accepted.

These are dated handoff facts, not a live market refresh.
