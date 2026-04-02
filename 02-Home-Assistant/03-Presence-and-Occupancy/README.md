# Presence and Occupancy System

This folder documents the system that determines whether the home is occupied and whether automation layers are allowed to act.

Presence is not treated as a convenience feature.

It is treated as a **permission engine** for the rest of the house.

---

## Purpose

Provide a stable, resilient occupancy signal that other automation layers can trust.

This signal is used to decide whether the system is allowed to:

- condition bedrooms  
- keep the den active  
- run occupancy-sensitive comfort logic  
- shift behavior between home and away states  
- support user-facing presence visibility in Apple Home  

---

## Design Role

This layer does not directly define HVAC behavior, appliance logic, or energy strategy.

Instead, it answers the first and most important system question:

> **Is the house considered occupied right now?**

Once that answer exists, other layers decide what they are allowed to do.

That is why this folder is separate from HVAC.

- **Presence** determines permission  
- **HVAC** determines climate behavior  

---

## Architecture Overview

This is not a single-app or single-device presence model.

It is a layered chain:

**iPhone location → Apple Home geofence automation → Eufy security mode → Docker Eufy bridge → Home Assistant occupancy logic**

That split is intentional.

- **Apple Home** uses phone location and native arrival/departure automation  
- **Eufy** holds the resulting home/away security state  
- **Docker** keeps the Eufy bridge running as a persistent backend service  
- **Home Assistant** converts that security state into a stable automation-grade occupancy signal  

This makes presence both:

- user-friendly at the front end  
- reliable for backend automation  

---

## Apple Home as the Geofence Backbone

Apple Home is the first step in the presence chain.

It uses phone location to determine real arrival and departure events.

### Arrival Automation

<p align="center">
  <img src="../Screenshots/945F33FA-836F-435E-B7F7-F18319222781.png" width="450"/>
</p>

This automation shows the Apple Home pattern for:

- **When the first person arrives home**

Apple Home uses that event to trigger a home-state action.

---

### Departure Automation

<p align="center">
  <img src="../Screenshots/5AA6FDD4-0739-4479-861E-28E20FB4B145.png" width="450"/>
</p>

This automation shows the Apple Home pattern for:

- **When the last person leaves home**

This is the backbone of the away-state transition.

### Why Apple Home Is Used Here

Apple Home is well-suited for the geofence portion of the problem because it already has:

- iPhone location awareness  
- first-person / last-person household logic  
- native HomePod / Apple ecosystem execution  
- reliable front-end automation behavior  

That makes it a strong trigger engine for household arrival and departure state changes.

---

## Eufy as the Stable Security-State Anchor

Apple Home is what detects location change, but Eufy is what provides the stable backend security state inside Home Assistant.

The presence model therefore does not rely on raw phone location directly in HA.

Instead, it relies on the resulting security mode.

### Integration View

<p align="center">
  <img src="../Screenshots/0766717C-E29D-47DB-AA8D-BBB8DF3CE6B7.jpeg" width="700"/>
</p>

This integration exposes the Eufy security environment into Home Assistant.

The important point is not just that cameras exist.

The important point is that the **security mode state becomes available as a reusable automation signal**.

### Source Entity

- `alarm_control_panel.eufybase`

### Interpretation Model

- `armed_away` → house is **not occupied**  
- `armed_home` / `disarmed` / `night` / `home` → house is **occupied**  
- `unknown` / `unavailable` → **fail open** (treat as occupied)  

This logic is exposed as:

- `binary_sensor.house_occupied_stable`

An alias sensor is also preserved for backward compatibility:

- `binary_sensor.bedrooms_house_occupied_stable`

---

## Why This Pattern Was Chosen

This design is stronger than relying on a single phone or GPS signal directly in Home Assistant.

Instead of asking:

> “Where is one device right now?”

the system asks:

> “What does the household presence system believe the house mode is?”

That gives the backend a much cleaner signal.

### Apple Home contributes:
- geofence detection  
- first-person / last-person logic  
- native household arrival/departure automation  

### Eufy contributes:
- persistent security mode  
- a clean home/away anchor  
- integration into Home Assistant through the Eufy bridge  

### Home Assistant contributes:
- stable interpretation  
- fail-open logic  
- reusable permission entities for other systems  

---

## Role of Docker in the Presence Chain

The Eufy integration depends on the Eufy bridge container running on the infrastructure server.

That Docker service is part of the presence architecture because it provides the persistent backend path that makes Eufy state available to Home Assistant.

Without that bridge:

- Eufy security state would not cleanly reach HA  
- stable occupancy interpretation would degrade  
- security-aware backend automations would lose their anchor  

So while Docker is documented elsewhere as infrastructure, it is also a direct dependency of this subsystem.

---

## Fail-Open Philosophy

If the system becomes uncertain, it does **not** assume the house is empty.

It assumes occupied.

### Why

A false-away result is more dangerous than a false-home result.

False-away could cause:

- unnecessary HVAC shutdown  
- loss of conditioning  
- invalid automation behavior  
- unsafe temperature drift  

False-home usually produces only a minor efficiency penalty.

So the system uses this rule:

> **If uncertain, assume occupied.**

This aligns with the broader design philosophy of the house:

- safety over efficiency  
- continuity over fragility  

---

## Relationship to Apple Home Beyond Geofencing

Apple Home is not only the geofence trigger source.

It is also the user-facing visibility layer for presence-related behavior.

That means Apple Home participates in two ways:

1. **as the front-end geofence trigger engine**
2. **as the household-facing communication and control layer**

This allows the user experience to stay native to the Apple ecosystem while Home Assistant handles backend automation decisions.

---

## Relationship to HVAC

This folder does not define how HVAC behaves.

It defines whether HVAC is allowed to behave.

Examples:

- bedrooms require `house_occupied_stable = on` before recovery logic is allowed  
- den activity logic is canceled when the house becomes away  
- away state is consumed by HVAC master logic to shut down non-baseline zones  

So while HVAC depends on this folder, presence itself remains an upstream subsystem.

---

## Stability Goal

The purpose of this layer is not to react to every tiny signal change.

The purpose is to produce a **stable, trustworthy occupancy state** that other automation layers can depend on.

That means this layer prioritizes:

- reliability  
- low ambiguity  
- clean interpretation  
- graceful behavior under uncertainty  

The goal is not maximum sensitivity.

The goal is **usable certainty**.

---

## Current Entity Model

### Primary Output

- `binary_sensor.house_occupied_stable`

### Compatibility Alias

- `binary_sensor.bedrooms_house_occupied_stable`

These entities exist so that:

- automations have a stable source of truth  
- older dashboards and cards do not break during cleanup  
- the architecture can evolve without a full system refactor  

---

## Why This Folder Exists Separately

This folder is intentionally separate from HVAC because the two solve different problems.

### Presence / Occupancy solves:

- who is home  
- whether the house is occupied  
- whether permission should be granted  
- what to do when state becomes uncertain  

### HVAC solves:

- which unit should run  
- what target temperature should be used  
- when recovery should begin  
- how active zones stay in compliance  

Presence is upstream of HVAC.

It is a decision input, not the climate system itself.

---

## What This Folder Contains

This folder includes the templates and helpers that define:

- stable occupancy state  
- Eufy-based security mode interpretation  
- fail-open handling under uncertainty  
- compatibility aliases for older entity names  

As the system grows, additional corroborating signals can be layered into this subsystem without forcing redesign of downstream automation layers.

---

## Design Summary

This is not a simple “who is home” feature.

It is the **permission layer** that determines whether the rest of the residential automation platform is allowed to behave as occupied or away.

The current implementation uses:

- **Apple Home** as the phone-location and geofence automation backbone  
- **Eufy** as the stable security-state anchor  
- **Docker** as the persistent bridge layer that feeds Home Assistant  
- **Home Assistant** as the backend interpreter of occupancy truth  

That makes the system:

- stable  
- layered  
- safe under uncertainty  
- easy for other automation systems to consume  
- and much more reliable than raw single-device presence logic
