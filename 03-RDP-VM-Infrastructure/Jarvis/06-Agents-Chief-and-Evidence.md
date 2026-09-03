# Agents, Chief, and Evidence

## Permanent rule

**Python reads raw data. AI reads evidence.**

Do not feed entire Home Assistant histories, system logs, databases, or repositories into a model.

Collectors gather raw data.

Normalizers standardize it.

Evidence builders calculate useful facts.

Agents receive bounded evidence.

## Domain agents

Initial domains include:

- HVAC
- Energy
- Server / Jarvis
- Media
- Network
- Home Assistant
- Local Events
- Presence

Agents analyze their own domain.

The Chief analyzes relationships between domains.

Example:

```text
Energy Agent:
household consumption +18%

HVAC Agent:
cooling runtime +31%

Weather evidence:
outdoor temperature +7°F

Chief:
energy increase is primarily HVAC-related;
no configuration change recommended yet.
```

The Chief should not reread every raw source. It should consume compact findings and summaries from specialists.

## Evidence contract

A common evidence structure should include:

```text
schema_version
domain
generated_at
period
sources
data_quality
facts
anomalies
missing_data
uncertainties
```

Standard evidence makes agents easier to replace, test, and compare.
