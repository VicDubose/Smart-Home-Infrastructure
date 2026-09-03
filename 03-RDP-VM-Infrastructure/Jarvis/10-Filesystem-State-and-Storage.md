# Filesystem, State, and Storage

Jarvis must distinguish code, persistent state, generated results, staging, and final data.

## Conceptual layout

```text
/opt/jarvis
    software / configuration / control-plane code

/var/lib/jarvis
    persistent Jarvis state and knowledge indexes

/var/log/jarvis
    operational logs

/home/onsiteadmin/Jarvis
    existing operational/state workspace
    jobs, reports, quarantine, audits, runtime artifacts

/home/onsiteadmin/rdp-scripts/Jarvis
    versioned results/proposals/review material
    NOT the live Jarvis runtime directory

/mnt/appdata/ha-services/local-events
    Local Events application/runtime tree

/mnt/media
    media library / staging-related storage contracts
```

The exact live locations should be verified from implementation when making operational decisions.

## Storage doctrine

- Final libraries must remain protected by validation gates.
- Runtime state should not be bulk-embedded into RAG as canonical documentation.
- Vector databases are rebuildable derived indexes.
- Backups are recovery copies, not live authority.
- Generated reports and old snapshots should not automatically become current design truth.
