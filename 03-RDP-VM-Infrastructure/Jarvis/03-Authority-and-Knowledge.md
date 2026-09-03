# Authority and Knowledge Model

Jarvis must understand that not every source represents the same kind of truth.

## Design / intent authority

**Smart-Home-Infrastructure**

This repository explains:

- what systems are intended to do;
- why design choices exist;
- how layers and subsystems relate;
- operational philosophy;
- future architecture.

This is the primary documentation corpus Jarvis should retrieve when asking, "What should happen?"

## Implementation authority

**Live Home Assistant server** and **live Jarvis Core**

These represent what is actually configured and deployed.

The live systems, not their Git backup copies, are the implementation authority.

## Runtime truth

Runtime collectors and direct system observation answer, "What is actually happening?"

Examples:

- Home Assistant state/history;
- systemd state;
- running processes;
- Docker state;
- SQLite queues;
- thermal state;
- media job state;
- Local Events job state;
- storage and filesystem state;
- application logs.

## Backup / recovery copy

**HA-Home-Server private GitHub repository**

This exists as a backup and recovery copy of Home Assistant configuration.

It is not the live Home Assistant server and should not be treated as the highest-confidence source of current implementation when live access is available.

Jarvis should not modify it as part of ordinary reasoning.

## Results / proposal repository

**rdp-scripts/Jarvis**

This is the cloud-synced, versioned results and remote-review location for Jarvis-produced work.

It may contain:

- reports;
- analyses;
- proposals;
- generated scripts;
- candidate automations;
- review artifacts;
- staged implementation material.

A result in this repository does not prove that production was changed.

## Conflict rule

```text
DESIGN says threshold should be 30
LIVE CONFIG says threshold is 45
OLD JARVIS REPORT proposed 35
RUNTIME shows behavior produced by 45

Correct interpretation:
- intended design: 30
- current implementation: 45
- previous proposal: 35
- runtime: reflects current 45 implementation
```

Jarvis must preserve these distinctions rather than flattening them into one "truth."
