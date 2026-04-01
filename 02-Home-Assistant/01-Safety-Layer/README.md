# Layer 0 — Safety Protection System

The Safety Layer is the highest-priority system in the Home Assistant architecture.

It operates independently of all other automation logic and is never overridden.

---

## Purpose

Prevent damage, unsafe conditions, and environmental risks by enforcing non-negotiable rules.

---

## Core Principles

- Always active  
- Overrides all other layers  
- Stateless enforcement (does not depend on schedules or presence)  
- Immediate response  

---

## Protections Implemented

### Freeze Protection

- Prevents pipe freezing during low-temperature conditions  
- Activates heating or load-based safeguards when thresholds are exceeded  

---

### Leak Detection

- Z-Wave leak sensors monitor critical locations  
- Triggers immediate alerts and optional automation responses  

---

### Extreme Temperature Safeguards

- Prevents unsafe indoor temperature conditions  
- Ensures minimum livable environment is maintained  

---

### Power Recovery Logic

- Ensures system returns to safe state after outage  
- Prevents uncontrolled startup conditions  

---

## System Behavior

This layer operates without regard to:

- energy cost  
- occupancy  
- schedules  

> Safety is enforced unconditionally.

---

## Device Dependencies

- Z-Wave leak sensors  
- Z-Wave temperature sensors  
- HVAC control entities  
- smart plugs (freeze protection loads)  

---

## Design Role

This layer forms the **foundation of the entire system**.

All other automation layers are built on top of it and must respect its decisions.
