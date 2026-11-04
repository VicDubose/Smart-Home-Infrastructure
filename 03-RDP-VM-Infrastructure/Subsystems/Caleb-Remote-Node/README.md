# Caleb Remote Node

Caleb's HP EliteBook-based Linux node is a remote helper node connected back to the Alabama environment through VPN.

It is not the primary Jarvis server.

## Roles

- remote Jellyfin/media helper;
- physical-disc ingest edge;
- VPN connectivity node;
- local Home Assistant monitoring site;
- severe-weather awareness;
- camera aggregation;
- router/network monitoring;
- remote access/testing.

## Media relationship

```text
CALEB DISC
    ↓
LOCAL RIP / STAGE
    ↓
VPN
    ↓
JARVIS / CORE
    ↓
VERIFY + IDENTIFY + VALIDATE
    ↓
MAIN LIBRARY
    ↓
OPTIONAL LATER SYNC BACK TO CALEB
```

Caleb's local storage is preferred for local playback but is not required for pipeline success.

A full local disk should not cause safe media ingestion to fail if Core has a valid storage path.

## Security

The remote node should have limited normal-user access, VPN-based internal reachability, and no unrestricted access to sensitive administrative or financial workflows.
