# SKYNET Topology and Node Roles

## SKYNET

SKYNET is the distributed infrastructure platform.

Jarvis is the orchestration and intelligence harness that spans it.

## SKYNET-CORE

Current Ubuntu infrastructure node.

Primary role: **execution and control plane**.

Responsibilities include:

- Docker infrastructure;
- Jellyfin;
- Open WebUI;
- Eufy services;
- physical-media tooling;
- media pipelines;
- databases and queues;
- systemd scheduling;
- automation;
- monitoring;
- validation;
- local events infrastructure;
- Jarvis control code;
- lightweight local AI where appropriate;
- KVM/libvirt virtualization;
- network/infrastructure appliances.

## SKYNET-AI

Future dedicated AI compute plane.

Primary role: **intelligence plane**.

Target responsibilities:

- local large-language-model inference;
- embeddings;
- vision;
- coding specialists;
- AI validation;
- model lifecycle management;
- Apple Foundation Models integration;
- MLX / Metal acceleration;
- difficult local reasoning;
- local-first agent execution;
- controlled cloud escalation.

## Storage plane

Future NAS / UGREEN-class storage becomes the long-term bulk data plane for:

- media;
- AI documents;
- datasets;
- backups;
- archives;
- cold model storage.

The harness should not depend on whether a path is backed by local disk or a future mounted NAS as long as stable mount and interface contracts are preserved.
