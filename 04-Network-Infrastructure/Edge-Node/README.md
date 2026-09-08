# Caleb Remote Edge Node

Caleb is the Texas-side **Edge node** for the Alabama Jarvis/Core environment. The node is intentionally not the authoritative server. It provides local Jellyfin playback/cache, raw-disc staging and handoff, Home Assistant monitoring, Local Events intelligence, remote support, telemetry, and controlled reverse synchronization from Jarvis/Core.

The design separates **catalog visibility** from **physical storage**: Caleb may see shared media even when the authoritative file lives only on Jarvis. Caleb's local media SSD is therefore a capacity-managed Edge cache rather than the permanent library authority.

## Current production baseline


| Component | Production state |
|---|---|
| Linux | Linux Mint 22.3 (Zena), Ubuntu Noble base |
| Kernel | 7.0.0-31-generic |
| Jellyfin | Running and healthy; HTTP 200 at release validation |
| Home Assistant | Running locally on port 8123 |
| Media SSD | `CALEB_EDGE_MEDIA`, mounted read/write at `/srv/media/External` |
| Staging | 50 GiB loop-backed ext4 at `/srv/staging` |
| VPN | OpenVPN tunnel to Alabama, `tun0` |
| Jarvis/Core | Reachable across VPN at `192.168.50.51` |
| Edge pull | `caleb-edge-pull.service`, production reverse-sync worker |
| Local Events | Dashboard + Sunday/Wednesday maintenance schedule |
| Node API | Rust/Axum telemetry service on port 8787 |
| Remote access | SSH + XRDP |


## Core design rule

```text
Caleb Edge node
    |  raw disc / telemetry / requests
    v
OpenVPN
    v
Jarvis/Core (Alabama)
    |  validation / authority / long-term library
    v
Reverse sync when Caleb has room
```

**Raw media flows Caleb → Jarvis. Finished approved media may flow Jarvis → Caleb.** A full Caleb cache must not prevent a valid ingest from being preserved on Jarvis.

## Power resilience and disaster role

Caleb's Edge node is also part of the Texas home's **power-outage and disaster-resilience architecture**. Because the server runs on a laptop, the laptop's internal battery acts as an integrated UPS for the compute layer. A utility outage does not immediately shut down Home Assistant, Jellyfin, Local Events, monitoring, or the other local services running on the node.

A separate **APC UPS protects the small network rack**, keeping the router, switching, and other essential network equipment online during an outage. The laptop battery and APC therefore protect different parts of the same system: the laptop keeps the Edge services alive, while the APC keeps the home's communication path alive.

For longer outages, a generator becomes the endurance tier by powering or recharging the laptop and APC-backed network equipment. The intended progression is **grid power -> battery-backed operation -> generator-supported operation**. This gives the household a continuing avenue for local networking, Home Assistant monitoring, weather and emergency information, cameras, media, and infrastructure status even when normal utility service is unavailable.

The goal is not unlimited runtime. It is to preserve a usable source of **power, communications, and information** for substantially longer than an ordinary unprotected home network. Generator operation remains separate from the network design and should follow normal electrical and carbon-monoxide safety requirements.

## Documentation map

| Folder | Purpose |
|---|---|
| `01-Architecture` | Role, boundaries, authority model, Alabama↔Texas design |
| `02-Hardware` | Live hardware and OS/software baseline |
| `03-Storage` | Internal disk, Edge SSD, staging ARM, retention/capacity rules |
| `04-Network-VPN` | VPN path, routes, remote access and service ports |
| `05-Jellyfin-Edge` | Jellyfin container, library layout and reverse sync |
| `06-Media-Pipeline` | Disc burn → Jarvis → archive → reverse-sync lifecycle |
| `07-Home-Assistant` | HA container, Media Command Center and telemetry |
| `08-Local-Events` | Tyler/Lindale board and scheduled maintenance |
| `09-Services-Timers` | Production systemd inventory and sanitized unit files |
| `10-Monitoring-Recovery` | Health checks and September 2026 SSD recovery runbook |
| `11-Disaster-Recovery` | Rebuild order, private-material checklist and acceptance tests |
| `12-Reference-Snapshot` | Sanitized production evidence from 2026-09-07 |
| `diagrams` | Mermaid architecture and workflow diagrams |

## Authority boundaries

Jarvis/Core remains the long-term processing and media authority. Caleb may ingest, cache, play, monitor and temporarily store. Caleb should not become the master copy simply because a title is currently cached there.

## Security boundary

This repository intentionally excludes passwords, private keys, VPN credentials, Home Assistant secrets, Jellyfin authentication secrets and API tokens. See `11-Disaster-Recovery/Private-Recovery-Checklist.md` for the material that must be backed up separately.

## Freeze state

The node was returned to **set-and-forget / frozen production** after the September 6 storage incident was repaired and the media worker was proven writing normally without new kernel storage faults.
