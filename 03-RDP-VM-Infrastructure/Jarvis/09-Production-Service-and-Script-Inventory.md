# Production Service and Script Inventory

This document is intentionally generated from the **live SKYNET-CORE implementation** rather than being guessed from the documentation repository.

The companion script in this update package is:

`tools/generate-jarvis-production-inventory.sh`

Run it on SKYNET-CORE and redirect the output into this file before the documentation commit if an exact inventory snapshot is desired.

## Inventory contract

For each active production component, capture:

| Field | Meaning |
|---|---|
| Component | Service/script/timer name |
| Purpose | Why it exists |
| Live path | Actual implementation path |
| Invoked by | systemd/service/parent process |
| Trigger | timer/event/manual/API |
| Domain | media/hvac/events/etc. |
| AI requirement | none/optional/required |
| Capability | requested model capability |
| Inputs/state | files/DB/API/queue |
| Outputs | job state/report/action |
| Failure behavior | retry/quarantine/stop |
| Status class | production/helper/test/legacy |

## Current known production families

The live inventory should cover at minimum:

- Jarvis media services and timers;
- ARM handoff/autostart/failure supervision;
- reverse library synchronization;
- media priority/router workers;
- Local Events dashboard/refresh/cleanup/backlog workers;
- Ollama service and resource policy;
- Jellyfin and related container services;
- Jarvis knowledge/harness components under `/opt/jarvis`;
- any active review/audit schedulers;
- supporting systemd units.

The generated inventory should be treated as an implementation snapshot. This design document remains the stable intent layer.
