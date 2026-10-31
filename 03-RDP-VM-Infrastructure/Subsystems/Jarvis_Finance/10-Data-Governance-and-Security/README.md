# Data Governance, Provenance, and Security

**Maps to parent README:** Sections 13 and 16

## Purpose

This folder defines how JARVIS Finance decides whether a fact is trustworthy, current, complete, and safe to publish. A value without source, date, unit, scope, and reconciliation state is not a complete financial fact.

## Core principles

- Evidence authority is claim-specific.
- Preserve original source dates separately from collection timestamps.
- Keep units explicit.
- Treat missing or conflicting evidence as unknown or review-only.
- Do not promote a valid historical record into a current fact.
- Keep private source material and credentials outside the public repository.

## Detailed pages

- [Provenance and freshness](provenance-and-freshness.md)
- [Privacy and security boundaries](privacy-and-security.md)
