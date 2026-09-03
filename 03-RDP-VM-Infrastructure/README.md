# RDP / SKYNET / Jarvis Infrastructure

This section documents the infrastructure layer that supports the household automation, media, AI, virtualization, monitoring, and operational tooling environment.

Historically this directory focused on the RDP server, Docker, and virtual machines. The environment has since evolved into a broader platform:

- **SKYNET** is the distributed infrastructure platform.
- **SKYNET-CORE** is the current Linux execution and orchestration node.
- **JARVIS** is the AI harness and operations brain that spans the platform.
- **SKYNET-AI** is the future dedicated AI compute plane.
- Live Home Assistant remains its own production implementation authority.
- GitHub repositories serve distinct documentation, backup, and review roles rather than being treated as interchangeable copies of production.

## Core mental model

```text
                         SKYNET
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
  SKYNET-CORE         SKYNET-AI          STORAGE / NAS
   EXECUTION          INTELLIGENCE            DATA
        │                  │                  │
        └──────────────────┼──────────────────┘
                           ▼
                         JARVIS
                         HARNESS
```

Jarvis is not one chatbot and not one model. It is the orchestration system around data collection, memory, evidence construction, model routing, tools, validation, reporting, proposals, and human approval.

## Documentation authority

```text
Smart-Home-Infrastructure
        ↓
DESIGN / INTENT AUTHORITY

LIVE HOME ASSISTANT + LIVE JARVIS CORE
        ↓
IMPLEMENTATION AUTHORITY

LIVE SERVICES / COLLECTORS / QUEUES / DB / STATE
        ↓
RUNTIME TRUTH

HA-Home-Server
        ↓
PRIVATE BACKUP / RECOVERY COPY

rdp-scripts/Jarvis
        ↓
RESULTS / PROPOSALS / REMOTE REVIEW
        ↓
HUMAN-APPROVED PROMOTION WHEN APPROPRIATE
```

The backup repository is not the live Home Assistant server. The Jarvis results repository is not the live Jarvis runtime. These boundaries are intentional.

## Directory map

- `Docker/` — containerized infrastructure services.
- `Host-System/` — Ubuntu host platform, storage, resource allocation, and management.
- `Virtualization/` — KVM/libvirt virtual machines and lab infrastructure.
- `Jarvis/` — Jarvis identity, harness, authority, knowledge, models, jobs, safety, inventory, and future AI node design.
- `Subsystems/` — major systems orchestrated or reviewed by Jarvis.
- `Screenshots/` — visual references for the documented infrastructure.

## Design rule

This repository explains **what the environment is designed to be and why**.

Live configuration and live state must be inspected from their production systems when exact current implementation or runtime behavior matters.
