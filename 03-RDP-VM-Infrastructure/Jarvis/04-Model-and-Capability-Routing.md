# Model and Capability Routing

Jarvis routes tasks by **capability**, not by hard-coded model name.

Typical capabilities include:

- embeddings
- operations-small
- general-small
- fast-general
- chief
- coding-local
- coding-senior
- vision
- cloud-cheap
- cloud-frontier

## Routing mental model

```text
REQUEST / SCHEDULED JOB
          ↓
DETERMINISTIC CLASSIFICATION
          ↓
EMBEDDING / SEMANTIC SIGNAL
          ↓
POLICY + ROUTER
          ↓
CAPABILITY REQUEST
          ↓
PROVIDER / NODE RESOLUTION
          ↓
MODEL
```

Embedding models provide semantic similarity, classification, and retrieval signals. They do not independently own hard policy decisions such as temperature limits, deadlines, permissions, or concurrency.

The deterministic scheduler remains responsible for:

- priority;
- deadline;
- resource availability;
- thermal state;
- model availability;
- task class;
- retry policy;
- whether a cloud escalation is permitted.

A more capable routing model may later resolve ambiguous requests, but hard operational policy remains deterministic.

## Two-tier semantic fabric

The long-term architecture may use an EmbeddingGemma instance on both SKYNET-CORE and SKYNET-AI.

If indexes are shared, both sides must use compatible:

- model artifact/version;
- embedding dimension;
- chunking profile;
- normalization contract.

The vector store is a derived search index, never an authority source.
