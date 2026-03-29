# Host System

This directory documents the physical host layer of the RDP infrastructure server.

The host system is the always-on foundation of the server environment. It provides the compute, storage, and operating-system layer that supports Docker containers, virtual machines, and infrastructure management services.

Rather than acting as a general-purpose desktop, the host is designed to operate as a stable infrastructure node for automation, media, and lab workloads.

---

## Purpose

The host system is responsible for:

- running the base operating system
- providing CPU, memory, and storage resources
- supporting Docker container workloads
- hosting the virtualization layer
- maintaining persistent uptime for automation services
- serving as the foundation of the smart home support infrastructure

This makes the host system the lowest operational layer of the RDP server stack.

---

## Hardware Platform

The current server platform is based on a compact mini desktop system used as a dedicated infrastructure node.

### Example Hardware Profile

- HP mini desktop platform
- AMD Ryzen-class CPU
- ~32 GB RAM
- dual-SSD layout for host + VM storage
- dedicated HDD / bulk storage for media

This hardware profile allows the server to run multiple VMs and containers simultaneously while maintaining low power draw and small physical footprint.

---

## Resource Allocation Strategy

The host is designed to reserve resources across three major areas:

- host operating system and management services
- Docker container workloads
- virtual machine workloads

### General Allocation Model

- **Host + Docker:** baseline reserved resources for always-on infrastructure
- **Windows VM:** administrative workstation workload
- **EVE-NG VM:** network lab / simulation workload

This allocation model keeps the system responsive while preserving headroom for future automation growth.

---

## Operating System Role

The host operating system is intended to function as a headless server platform.

Its responsibilities include:

- Docker runtime support
- KVM / virtualization support
- storage mounting and management
- networking and interface management
- service startup and uptime
- infrastructure monitoring

This allows higher-level services to remain independent of a user desktop environment.

---

## Storage Roles

The host uses separated storage roles to reduce contention between workloads.

### Intended Storage Layout

- **System SSD**  
  host operating system, Docker runtime, service configuration

- **VM Storage SSD**  
  Windows VM disk, EVE-NG VM disk, snapshots

- **Media / Bulk Storage HDD**  
  Jellyfin media library and non-critical bulk storage

This layout improves:

- VM performance consistency
- media storage isolation
- service reliability
- easier backup planning

---

## Why the Host Layer Matters

The host system is what allows the rest of the environment to function as infrastructure rather than a personal workstation.

Because Home Assistant helper services, presence-support services, utility scrapers, and lab tooling all depend on continuous availability, the host layer must prioritize:

- uptime
- recoverability
- storage separation
- low operational overhead

This is what turns the RDP server into a true 24/7 infrastructure node.
