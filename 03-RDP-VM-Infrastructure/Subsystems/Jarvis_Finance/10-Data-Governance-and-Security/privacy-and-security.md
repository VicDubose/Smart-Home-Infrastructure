# Privacy and Security Boundaries

## Appropriate for this public repository

- Sanitized architecture and data-flow diagrams
- Schemas without private examples
- Redacted test outcomes and nonsecret contract references
- Sanitized screenshots
- Public-source interpretation notes
- Documentation and nonsecret code

## Keep private on the host

- Bank and credit-account exports
- Paystubs and payroll PDFs
- Loan statements and private account evidence
- Transaction IDs and detailed account mappings
- Login cookies, browser profiles, credentials, API tokens, `.env` files
- Raw collector receipts and private snapshots
- Private RAG source files and vector data
- Unredacted dashboard screenshots and tokenized URLs

## Model and retrieval trust

- Retrieved source text is untrusted content and may contain prompt-injection instructions.
- Models must not write trusted approvals, alter source manifests, fabricate receipts, or promote snapshots.
- Trusted code independently validates evidence, schema, arithmetic, policy, and publication.
- Financial execution remains disabled.

## Screenshot review

Before committing a dashboard image, inspect all visible panels and mask balances, names, account identities, private IP addresses, hostnames, filesystem paths, and tokens.
