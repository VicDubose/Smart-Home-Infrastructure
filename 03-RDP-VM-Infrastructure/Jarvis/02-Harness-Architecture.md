# Jarvis Harness Architecture

The harness is the control system around every AI model.

```text
                    JARVIS HARNESS
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
      COLLECT           REMEMBER          EXECUTE
        │                 │                 │
        ▼                 ▼                 ▼
      APIs              RAG               Tools
      Logs              Git               Scripts
      SQL               History           APIs
      Files             Incidents         Validation
        │                 │                 │
        └─────────────────┼─────────────────┘
                          ▼
                      NORMALIZE
                          ↓
                       EVIDENCE
                          ↓
                        ROUTER
                          ↓
             ┌────────────┼────────────┐
             ▼            ▼            ▼
           HVAC         ENERGY       SERVER
           AGENT         AGENT        AGENT
             └────────────┼────────────┘
                          ▼
                        CHIEF
                          ↓
                  REPORT / PROPOSAL
                          ↓
                      VALIDATION
                          ↓
                     HUMAN REVIEW
                          ↓
                  APPROVED ACTION
```

## Major harness components

1. Collectors
2. Normalizers
3. Evidence builders
4. Knowledge / RAG
5. Job database
6. Router
7. Model provider / capability resolver
8. Agent runner
9. Chief aggregator
10. Policy and safety engine
11. Validator
12. Approval and promotion workflow

These components should remain independent. Jarvis should never collapse into one enormous `jarvis.py`.

## Stable abstraction rule

Agents request capabilities, not concrete model names.

Example:

```text
HVAC agent
    ↓
requires: fast-general
    ↓
provider resolves current node/model
```

This allows the future SKYNET-AI node to be added without redesigning every agent.
