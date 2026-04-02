# Presence and Occupancy System

This folder defines the system that determines whether the home is considered occupied and whether automation layers are allowed to act.

Presence is not treated as a convenience feature.

It is treated as a **permission engine** for the rest of the house.

---

## Purpose

Provide a stable, resilient occupancy signal that other automation layers can trust.

This signal is used to determine whether the system is allowed to:

- condition bedrooms  
- keep the den active  
- run occupancy-sensitive comfort logic  
- shift behavior between home and away states  
- support user-facing presence visibility in Apple Home  

---

## Design Role

This layer does not directly control HVAC, appliances, or energy behavior.

Instead, it answers the first and most important system question:

> **Is the house considered occupied right now?**

Once that answer exists, other systems decide what they are allowed to do.

This is why this folder is separate from HVAC:

- **Presence → determines permission**  
- **HVAC → determines climate behavior**

---

## Architecture Overview

Presence is not derived from a single device or app.

It is constructed as a layered system:

**iPhone location → Apple Home → Eufy security mode → Docker bridge → Home Assistant**

Each layer has a specific role:

- **Apple Home** detects arrival and departure using iPhone location  
- **Eufy** stores the resulting home/away state as a security mode  
- **Docker (Eufy Bridge)** exposes that state reliably into Home Assistant  
- **Home Assistant** converts it into a stable automation-grade occupancy signal  

This separation makes the system:

- user-friendly at the front end  
- reliable at the automation layer  

---

## Apple Home as the Geofence Backbone

Apple Home is the entry point for presence detection.

It uses iPhone location and household awareness to determine:

- when the first person arrives home  
- when the last person leaves home  

### Unified Presence Automation View

<p align="center">
  <img src="../01-Apple-Home/Screenshots/IMG_1335.png" width="700"/>
</p>

This single view represents the full presence automation model.

Apple Home manages arrival and departure as a **unified household state**, not as separate independent automations.

---

## Role of Apple Home in the System

Apple Home is responsible for:

- geofence detection (iPhone location)  
- first-person / last-person household logic  
- triggering home ↔ away transitions  
- initiating system-wide state changes  

It acts as the **front-end decision layer** for presence.

---

## Eufy as the Security-State Anchor

Apple Home detects presence changes, but Eufy provides the **stable backend state**.

The system does not rely on raw GPS inside Home Assistant.

It relies on the resulting security mode.

### Source Entity

- `alarm_control_panel.eufybase`

### Interpretation Model

- `armed_away` → house is **not occupied**  
- `armed_home` / `disarmed` / `night` / `home` → house is **occupied**  
- `unknown` / `unavailable` → **fail open** (treated as occupied)  

This is exposed as:

- `binary_sensor.house_occupied_stable`

Compatibility alias:

- `binary_sensor.bedrooms_house_occupied_stable`

---

## Role of Docker in the Presence Chain

The Eufy bridge container provides the connection between Eufy and Home Assistant.

This makes Docker part of the presence system, not just infrastructure.

Without it:

- Eufy state would not reliably reach Home Assistant  
- occupancy logic would degrade  
- automation permission would become unstable  

---

## Why This Pattern Was Chosen

Instead of asking:

> “Where is a device right now?”

the system asks:

> “What is the current household state?”

This produces a much cleaner and more reliable signal.

### Apple Home provides:
- location-based event detection  
- household-level presence logic  

### Eufy provides:
- persistent home/away state  
- security-aligned system mode  

### Home Assistant provides:
- stable interpretation  
- fail-safe handling  
- reusable automation signals  

---

## Fail-Open Philosophy

If the system becomes uncertain, it does **not** assume the house is empty.

It assumes occupied.

### Reasoning

A false-away state is more dangerous than a false-home state.

False-away could cause:

- HVAC shutdown during occupancy  
- loss of conditioning  
- unsafe temperature drift  
- incorrect automation behavior  

False-home results in minor efficiency loss.

So the system follows:

> **If uncertain, assume occupied**

---

## Relationship to Apple Home (UI Layer)

Apple Home serves two roles:

1. **Presence trigger system (geofence + household logic)**  
2. **User-facing control and visibility layer**

This keeps:

- automation logic in Home Assistant  
- interaction and feedback in Apple Home  

---

## Relationship to HVAC

This folder does not define HVAC behavior.

It defines whether HVAC is allowed to operate.

Examples:

- bedrooms require `house_occupied_stable = on` before running recovery logic  
- den logic is disabled when the house is away  
- HVAC master logic uses away state to shut down non-essential zones  

Presence is therefore:

> **an upstream dependency of HVAC, not part of HVAC**

---

## Stability Goal

This system is not designed for maximum sensitivity.

It is designed for **maximum reliability**.

It prioritizes:

- clean binary state  
- low ambiguity  
- resilience to failure  
- predictable behavior  

The goal is:

> **usable certainty, not noisy precision**

---

## Current Entity Model

### Primary Output

- `binary_sensor.house_occupied_stable`

### Compatibility Alias

- `binary_sensor.bedrooms_house_occupied_stable`

These ensure:

- stable automation inputs  
- backward compatibility  
- flexibility for future redesign  

---

## What This Folder Contains

- Eufy-based occupancy interpretation  
- stable presence templates  
- fail-open handling logic  
- compatibility entity aliases  

This layer is intentionally minimal and focused.

---

## Design Summary

This is not a basic presence feature.

It is a **multi-layer occupancy system** that separates:

- detection (Apple Home)  
- state (Eufy)  
- transport (Docker bridge)  
- interpretation (Home Assistant)  

The result is a system that is:

- stable  
- resilient  
- safe under uncertainty  
- easy for other systems to consume  
- significantly more reliable than raw GPS or single-device presence tracking  
