# AI Compute Evolution

Jarvis is designed so that intelligence hardware can evolve without rewriting the harness.

## Stage 1 — SKYNET-CORE only

Current Core provides lightweight local AI, retrieval, routing support, classification, and carefully governed generative work.

The primary constraint is sustained CPU inference and thermal headroom.

The correct response is not to build the harness around the limitation. The correct response is to keep stable job/capability interfaces and serialize work until more compute exists.

## Stage 2 — Earlier dedicated AI-node design

An earlier design checkpoint used an M4 Max-class Mac Studio with approximately 64 GB unified memory and one large specialist slot at a time.

That architecture established the lasting node split:

```text
SKYNET-CORE = DOES
SKYNET-AI   = THINKS
STORAGE     = STORES
```

## Stage 3 — Current expanded long-term AI vision

The expanded design is a single dedicated household AI appliance with much more unified memory, multiple specialist models, Apple-native AI integration, and controlled model lifecycle management.

The current long-term concept favors a **Mac Studio Ultra-class system with roughly 256 GB unified memory** when the goal includes both a 20B everyday reasoning model and a 120B deep-local reasoning model plus specialists.

The system should still avoid keeping every large model hot without reason.

Conceptually:

```text
APPLE FOUNDATION MODEL
        │
        ├── fast native / OS-integrated work
        │
        ├── gpt-oss-20B     everyday local reasoning
        │
        ├── gpt-oss-120B    deep local reasoning
        │
        ├── coding specialist
        │
        ├── vision specialist
        │
        └── embeddings / reranking
                     │
                     ▼
              JARVIS HARNESS
                     │
              tools + memory
                     │
           cloud only if required
```

## Important rule

Models do not "stack" into one giant model.

The router selects the correct brain for the job.

Examples:

```text
simple HA action
    → Apple / tiny local

routine infrastructure reasoning
    → local general worker

large difficult technical analysis
    → deep local model

repeated local failure / exceptional architecture problem
    → human-approved cloud escalation
```

This keeps local intelligence cost-efficient while preserving access to frontier capability when needed.

## Apple as an integration layer

The long-term goal is a stable Jarvis-facing abstraction such as:

```text
Jarvis.ask(task)
      ↓
router
      ↓
Apple
local-small
local-medium
local-large
cloud-cheap
cloud-frontier
```

Everything else in the environment should talk to Jarvis rather than directly coupling itself to a particular provider.
