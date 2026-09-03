# Jarvis

Jarvis is a local-first household and infrastructure AI operating system built as a harness around models, tools, evidence, memory, policies, and human approval.

Jarvis is not a computer and is not a single LLM.

The core operating model is:

```text
ANALYZE
   ↓
COMPARE
   ↓
REPORT
   ↓
PROPOSE
   ↓
VALIDATE
   ↓
HUMAN REVIEW
   ↓
APPROVED ACTION
```

Jarvis may read, analyze, compare, summarize, report, recommend, and stage proposed work. Production-changing actions remain governed by deterministic controls and explicit human approval.

## Permanent principles

1. Python and deterministic tooling read raw data. AI reads bounded evidence.
2. Agents analyze domains. The Chief analyzes relationships between domains.
3. AI proposes. Deterministic software validates. Humans authorize.
4. Production is not a free-write playground for models.
5. Every AI job has bounded inputs, bounded authority, a defined capability, and a defined output.
6. Models are replaceable workers behind stable capability interfaces.
7. Runtime facts must not be confused with design intent, backup copies, or old proposals.
8. Local intelligence handles normal operations; external frontier AI is an escalation tier, not the foundation.

## Documents

- `01-Core-Vision.md`
- `02-Harness-Architecture.md`
- `03-Authority-and-Knowledge.md`
- `04-Model-and-Capability-Routing.md`
- `05-Jobs-Scheduling-and-Resource-Governor.md`
- `06-Agents-Chief-and-Evidence.md`
- `07-Validation-Approval-and-Promotion.md`
- `08-SKYNET-Topology-and-Node-Roles.md`
- `09-Production-Service-and-Script-Inventory.md`
- `10-Filesystem-State-and-Storage.md`
- `11-AI-Compute-Evolution.md`
