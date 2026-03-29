# Docker Infrastructure

This directory documents the containerized service layer running on the RDP infrastructure server.

Docker is used to host lightweight, persistent services that support the smart home automation platform, remote media access, and utility-data collection without requiring full virtual machines for each workload.

In this environment, containers provide the always-on service layer that sits between the Ubuntu host system and the larger smart home stack.

---

## Purpose

The Docker layer is used to:

- keep core support services isolated from the host OS
- reduce overhead compared to running separate VMs
- simplify deployment, recovery, and maintenance
- provide persistent infrastructure services for Home Assistant and related tooling
- ensure critical integrations restart automatically after host reboot
- provide external validation data for the energy automation system (utility-side verification)
  
This makes Docker one of the most important operational layers in the infrastructure stack.

---

## Runtime Model

The host system uses:

- **Docker Engine**
- **docker-compose**
- restart policies for automatic recovery
- bridged LAN access for service visibility inside the home network

The containers are designed to behave like internal infrastructure services rather than public-facing internet applications.

All service access remains:

- local to the LAN
- VPN-accessible through ASUS Instant Guard when remote
- hidden from direct public exposure

---

## Service Design Philosophy

Containers are used here for services that need to be:

- persistent
- lightweight
- modular
- easy to update
- isolated from the host operating system

Rather than installing these services directly onto Ubuntu, Docker allows each one to run in its own environment with its own image, configuration, ports, and volumes.

This keeps the infrastructure cleaner and makes it easier to back up, rebuild, or migrate services later.

---

## Active Containerized Services

### 1. Jellyfin

**Purpose:** self-hosted media streaming server

Jellyfin provides:

- centralized media library hosting
- streaming to local devices
- VPN-based remote streaming when away from home
- user profile and access control
- metadata and poster management

In this environment, Jellyfin functions as the media-service layer of the home lab and is intentionally isolated from the main automation stack so it does not interfere with Home Assistant operations.

Typical access path:

- local: `http://server-ip:8096`
- remote: VPN → LAN → Jellyfin

---

### 2. Eufy Bridge

**Purpose:** bridge service between Eufy security devices and Home Assistant

This container is one of the most important services in the environment because it acts as part of the backbone of the presence and security system.

The Eufy bridge is used to:

- expose Eufy security state into Home Assistant
- track security mode changes
- support home / away logic
- help drive front-end smart home behavior
- support the presence-detection chain used by the larger automation design

This service is especially important because it helps connect camera and security-system behavior to the rest of the smart home automation platform.

---

### 3. Alabama Power Scraper

**Purpose:** collect utility consumption data and send it into Home Assistant

This service is implemented as a Python-based automation workload that logs into the Alabama Power customer portal, scrapes Average Daily Usage (kWh), and publishes the value into Home Assistant.

Its role is to provide a secondary source of truth for energy tracking and validation within the Layer 3 energy system.

⸻

Role in the Energy System

Unlike device telemetry (Tesla Powerwall, solar inverter, etc.), which represents real-time system-side measurements, this scraper provides utility-side consumption data.

It is used to:
- track daily grid energy usage from the utility perspective
- compare against Tesla Powerwall / gateway real-time data
- validate internal energy measurements
- detect discrepancies between system-reported and utility-reported usage
- support long-term energy optimization analysis		

This enables the system to verify:

whether the home’s internal energy model matches actual billed consumption

---

Integration with Tesla Powerwall

Tesla Powerwall provides:
- real-time energy flow
- battery state of charge
- solar production
- instantaneous grid import/export  

The Alabama Power scraper complements this by providing:
	
	•	delayed but authoritative utility-reported usage

Together, they form a dual-layer validation model:

Powerwall (real-time system view) + Utility (reported usage) = validated energy model

---

Execution Model

The scraper runs on a scheduled basis aligned with the utility update cycle:
- typically executed twice per day
- allows time for Alabama Power to update usage data
- keeps Home Assistant synchronized with utility reporting

---

Operational Importance

This service is considered:

Important but non-critical
- does not impact safety or comfort systems
- does not affect real-time automation behavior
- enhances accuracy and long-term optimization and automation reliability

  ---
  
Design Notes
- implemented as a lightweight Python automation workload
- containerized for isolation and persistence
- uses Playwright for browser automation
- avoids reliance on undocumented APIs
- designed with fallback logic for page changes
	
Sensitive credentials and tokens are managed via environment variables and are not stored in source control.

---

## Operational Importance

Not all containers in this environment have the same level of criticality.

### Critical Container

#### Eufy Bridge
This is considered a **core smart home support service** because it directly contributes to:

- presence logic
- security-state transitions
- camera-mode automation behavior

If this container fails, parts of the home’s presence-aware behavior become degraded.

---

### Important but Non-Critical

#### Alabama Power Scraper
This service is operationally important because it supports energy analysis and long-term optimization, but it does not directly stop the home from functioning if it is temporarily unavailable.

#### Jellyfin
Jellyfin is a quality-of-life and media service. It is useful and production-running, but it is not part of the critical automation path.

---

## Startup and Recovery Model

All containers are configured to automatically recover after reboot or interruption.

The intended behavior is:

- Ubuntu host boots
- Docker daemon starts
- containers automatically restart
- services return without manual intervention

This allows the system to operate as a true infrastructure node rather than a manually managed lab box.

The design goal is **hands-off recovery** for routine host restarts.

---

## Docker Networking Model

Containers are deployed as internal services and are intended to be accessed from inside the local environment.

### Access Characteristics

- LAN accessible
- bridged into the internal network environment
- remote access available only through VPN
- no direct public port exposure

### Security Model

The Docker layer is protected by the broader infrastructure design:

- services remain internal
- ASUS router/firewall policies protect the edge
- ASUS Instant Guard VPN acts as the remote access point
- no public-facing service publishing is required for normal operation

This keeps the container layer simple and secure.

---

## Storage Behavior

Containers use persistent storage through mapped volumes.

This is important because container images are disposable, but service data is not.

Persistent data includes things like:

- Jellyfin configuration and metadata
- media library mappings
- Eufy bridge configuration/state
- scraper scripts and execution context
- logs and service-specific data

### Media Placement Strategy

Jellyfin content follows a tiered storage model:

- active / current media may reside on SSD during setup or transition
- long-term media storage is intended for the dedicated HDD
- host and automation-critical services remain on SSD-backed storage

This helps separate:

- performance-sensitive workloads
- VM disk activity
- long-term media storage

---

## Resource Efficiency

One of the reasons Docker is used here instead of additional VMs is efficiency.

Compared to a VM, a container:

- starts faster
- uses less memory
- has lower storage overhead
- is easier to replace
- is easier to version and redeploy

That makes containers ideal for lightweight service workloads like:

- APIs
- bridge services
- scrapers
- media servers

This design allows the RDP infrastructure server to support several services at once without unnecessary virtualization overhead.

---

## Deployment Model

The Docker environment is designed around compose-based management.

This makes it easier to:

- keep service definitions readable
- define ports, volumes, and restart rules in one place
- rebuild services consistently
- migrate the environment later if needed

The broader design also supports future growth and eventual migration into a more formal Compose-based architecture if the infrastructure stack is later moved or rebuilt.

---

## Example Runtime Snapshot

The live environment currently demonstrates the following behavior:

- Jellyfin container running and healthy
- Eufy bridge container running continuously
- low memory overhead compared to total system RAM
- minimal CPU usage under normal conditions
- ports published only for internal / VPN-based access

This validates Docker as a stable long-running service layer for the infrastructure.

---

## Example Compose Pattern

The following example reflects the design style used in this environment:

```yaml
version: "3.8"

services:
  jellyfin:
    image: jellyfin/jellyfin:latest
    container_name: jellyfin
    restart: unless-stopped
    ports:
      - "8096:8096"
    volumes:
      - ./jellyfin/config:/config
      - ./jellyfin/cache:/cache
      - ./media:/media

  eufy_ws:
    image: bropat/eufy-security-ws:latest
    container_name: eufy_ws
    restart: unless-stopped
    ports:
      - "3000:3000"
    volumes:
      - ./eufy:/data

  alabama_power_scraper:
    build: ./alabama-power
    container_name: al_power_scraper
    restart: unless-stopped
    volumes:
      - ./alabama-power:/app
