# A — Strategy, Constraints, and Long-Term Planning

**Maps to parent README:** Section 8

## Purpose

A records user-approved goals, constraints, preferences, and long-term planning intent. It gives the system a policy context for comparing alternatives; it is not a source of current balances, bank deposits, loan principal, APRs, or market prices.

## Strategy domains

- Emergency reserves and liquidity floors
- Debt priorities and affordability constraints
- Savings goals and contribution schedules
- Housing and real-estate planning
- Retirement and investment constraints
- Near-term project obligations
- User-approved priorities and exceptions

## Evidence boundary

A strategy preference can be authoritative for what the user wants. It cannot prove what cash is currently available or what interest rate a lender is charging. Those facts must come from current, qualified source evidence.

The Real Estate Strategy V1.4 material is described in the parent README as a policy-level view. Sensitive property details and private agreements do not belong in this public folder.

## Current status

Strategy topics are documented and the typed Finance Decision Contract has design-only approval for isolated testing. A fully accepted integration binding user profile and policy to fresh financial facts is not established.

## Output contract

A should provide versioned goals and constraints with provenance and effective dates. Downstream systems may compare validated alternatives against them, but cannot silently change the user's policy or execute a financial action.

See the [parent strategy section](../README.md#8-a--strategy-constraints-and-long-term-planning).
