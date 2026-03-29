# Host System

This directory documents the host system layer of the RDP infrastructure server.

The host system is the foundational layer of the entire environment. It is responsible for maintaining continuous operation of all services, allocating system resources, and ensuring that virtualization and container workloads coexist without interference.

Unlike a traditional desktop, the host is designed to function as a **dedicated infrastructure node** with a focus on stability, uptime, and controlled resource distribution.

---

## Role of the Host System

The host system operates as the **control and execution layer** beneath all higher-level services.

Its responsibilities include:

- managing CPU and memory allocation across workloads  
- maintaining storage separation between system, VM, and media data  
- running the Docker runtime for persistent services  
- supporting KVM-based virtualization  
- providing system monitoring and management interfaces  
- ensuring all services recover automatically after restart  

This allows the system to function as a **24/7 infrastructure platform** rather than a user-operated machine.

---

## Host Operating System

### Ubuntu Server

The host runs Ubuntu Server in a headless configuration.

This provides:

- low overhead operation  
- direct access to Linux-native virtualization (KVM)  
- native Docker support  
- stable long-term runtime for automation services  

No desktop environment is used, ensuring that all resources are dedicated to infrastructure workloads.

---

## Infrastructure Management (Cockpit)

<p align="center">
  <img src="../Screenshots/IMG_1350.png" width="600"/>
</p>

Cockpit is used as the primary management interface for the host system.

The screenshot above shows:

- active virtual machines running on the host  
- system-level visibility into infrastructure workloads  
- centralized control of VM lifecycle and system resources  

Cockpit enables:

- real-time CPU and memory monitoring  
- storage and disk management  
- VM control through libvirt integration  
- service visibility across the host  

This eliminates the need for separate hypervisor management tools.

---

## Container Runtime Visibility

<p align="center">
  <img src="../Screenshots/IMG_1354.png" width="600"/>
</p>

Docker containers run directly on the host system and provide persistent support services.

The host is responsible for:

- maintaining container uptime  
- managing container resource usage  
- ensuring restart policies are honored  
- isolating container workloads from virtual machines  

This ensures that lightweight services do not interfere with heavier VM workloads.

---

## Resource Allocation Strategy

The host system is intentionally balanced to support multiple workload types simultaneously.

### Memory Allocation

- **Total System Memory:** ~32 GB  
- **Windows 11 VM:** ~10 GB  
- **EVE-NG VM:** ~14 GB  
- **Host + Docker:** ~8 GB  

This allocation ensures:

- sufficient memory for virtualization workloads  
- stable operation of containerized services  
- headroom for system processes and monitoring  

---

### CPU Allocation

- **Windows VM:** 2 vCPU  
- **EVE-NG VM:** 4 vCPU  
- **Host + Docker:** remaining CPU threads  

This distribution prioritizes:

- lab performance for EVE-NG  
- responsiveness of the Windows admin environment  
- consistent performance for always-on services  

---

## Storage Coordination

The host system manages multiple storage tiers to prevent workload contention.

### Storage Layout

- **Primary SSD**  
  - Ubuntu OS  
  - Docker runtime and volumes  
  - system configuration  

- **Secondary SSD**  
  - virtual machine disk images  
  - snapshots and lab data  

- **HDD Storage**  
  - Jellyfin media library  
  - bulk storage and non-critical data  

This separation ensures:

- VM disk I/O does not impact system services  
- media streaming does not affect automation workloads  
- predictable performance across all layers  

---

## Operational Behavior

At runtime, the system behaves as follows:

1. Host system boots  
2. Docker services initialize automatically  
3. Virtual machines become available  
4. Cockpit provides system visibility  
5. Infrastructure services remain continuously available  

This allows the server to function without manual intervention after startup.

---

## Stability Design

The host system is designed to prevent common failure modes:

- Windows updates do not affect infrastructure  
- container restarts do not impact VM stability  
- lab experimentation does not affect production services  
- storage separation prevents I/O bottlenecks  

This creates a resilient environment where:

- automation continues running  
- services recover automatically  
- system behavior remains predictable  

---

## Why the Host Layer Matters

The host system is what transforms the environment from a collection of tools into a **cohesive infrastructure platform**.

It ensures:

- continuous uptime for smart home support services  
- controlled interaction between containers and VMs  
- reliable execution of automation-related workloads  
- centralized management of all system components  

Without this layer, the system would behave like a workstation.

With it, the system behaves like a **dedicated infrastructure server**.
