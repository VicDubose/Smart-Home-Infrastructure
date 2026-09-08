# Media Pipeline

```mermaid
flowchart TD
  DISC[DVD/Blu-ray at Caleb] --> RAW[Raw burn/rip]
  RAW --> STAGE[/srv/staging]
  STAGE --> VPN[VPN handoff]
  VPN --> CORE[Jarvis/Core]
  CORE --> VERIFY[Validate / identify / name]
  VERIFY --> LIB[Authoritative library]
  LIB --> SPACE{Caleb has reserve?}
  SPACE -->|yes| PULL[caleb-edge-pull]
  PULL --> LOCAL[Caleb local cache]
  SPACE -->|no| REMOTE[Jarvis-only; sync later]
  CORE --> CONF[Confirmed receipt]
  CONF --> CLEAN[72-hour confirmed cleanup]
```
