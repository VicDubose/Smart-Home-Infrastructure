# Alabama ↔ Texas Architecture

Caleb operates remotely in Texas and reaches the Alabama home network through an OpenVPN tunnel hosted by the home ASUS router.

```mermaid
flowchart LR
  subgraph TX[Texas — Caleb Edge]
    C[Caleb Edge Node]
    JF[Jellyfin Edge]
    HA[Home Assistant]
    LE[Local Events]
    ST[Raw Staging]
  end

  subgraph AL[Alabama — Core]
    VPN[ASUS OpenVPN Server]
    CORE[Jarvis / Core
192.168.50.51]
    LIB[Authoritative Media Library]
  end

  C --> VPN
  VPN --> CORE
  ST -->|raw handoff| CORE
  CORE --> LIB
  LIB -->|reverse sync when capacity permits| JF
  HA -->|telemetry / reachability| CORE
  LE -->|temporary AI execution path| CORE
```

The preferred behavior is split tunneling: ordinary Texas internet traffic stays local while Alabama home-lab traffic uses the VPN.
