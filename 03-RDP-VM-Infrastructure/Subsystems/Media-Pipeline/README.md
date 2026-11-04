# Jarvis Media Pipeline

The media subsystem turns physical and remote media intake into validated Jellyfin library updates.

## Goal

```text
DISC / REMOTE INTAKE
        ↓
DETECT + ROUTE
        ↓
RIP / COPY / RECEIVE
        ↓
STAGE
        ↓
REGISTER JOB
        ↓
TECHNICAL VALIDATION
        ↓
AI REVIEW WHEN NEEDED
        ↓
DUPLICATE / COLLISION CHECKS
        ↓
MOVE ONLY ON PASS
        ↓
JELLYFIN REFRESH
        ↓
ARCHIVE JOB STATE
```

## Sacred move rule

```text
NO VALIDATION PASS
        =
NO FINAL LIBRARY MOVE
```

AI does not directly move files. Deterministic Jarvis/Python controls filesystem changes, collision protection, staging, queue state, and final movement.

## Concurrency

Physical ripping may happen in parallel.

Validation converges through a controlled lane so validators, AI jobs, and final moves do not race each other.

## Caleb remote node

Caleb's laptop is a remote helper/media edge node, not the primary Jarvis authority.

If local storage is constrained, the ingest pipeline should continue by transferring material to the main Jarvis/Core side, preserving the media safely, and allowing later sync back to Caleb when desired.

Catalog visibility and physical storage location are separate concepts.
