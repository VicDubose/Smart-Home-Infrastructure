# HomeKit Bridge

## Overview

HomeKit Bridge is the integration layer that connects **Home Assistant’s internal automation system** to **Apple Home’s user-facing control surface**.

Its purpose is not to expose everything from Home Assistant.  
Instead, it selectively publishes only the entities that are useful for:

- human interaction
- family-facing controls
- Siri voice interaction
- status visibility
- appliance and system notifications

---

## Architecture in Practice

<img src="../screenshots/IMG_1317.png" width="200"/>

This is the real Apple Home interface powered by the HomeKit Bridge.  
Everything visible here is intentionally exposed — nothing more.

---

## Design Philosophy

The bridge follows a strict **allowlist-first approach**:

- expose only useful, human-facing entities  
- hide noisy infrastructure entities  
- keep Tesla / Powerwall / router telemetry out of Apple Home  
- prevent adaptive recovery and HVAC helper noise  
- separate security from general UI  

---

## Bridge Structure

### Bridge 1 — Security + Helpers

Handles:

- Eufy HomeBase status
- guard mode + alarm panel
- washer/dryer state helpers
- Shelly H&T sensors (temperature + humidity)

---

### Bridge 2 — Household UI

Handles:

- climate controls
- locks
- plugs and switches
- lights
- camera snapshots
- TVs and media devices

---

## Example: Camera + Access Layer

<img src="../screenshots/IMG_1323.png" width="200"/>

Camera snapshots and access points are exposed in a way that’s immediately usable without needing backend context.

---

## Commonly Exposed Entities

- climate entities  
- locks  
- plugs / switches  
- helper booleans  
- temperature / humidity sensors  
- water leak sensors  
- camera snapshots  
- appliance status  

---

## What Is Intentionally Hidden

- adaptive recovery logic  
- HVAC backend automations  
- Tesla / Powerwall data  
- router / network telemetry  
- helper timers and internal states  

---

## Communication Role

HomeKit Bridge is also the **communication layer** between HA and users.

It carries:

- alert flags  
- appliance state  
- presence state  
- system status  

---

## Siri Voice Announcement Pattern

<img src="../screenshots/IMG_1321.png" width="200"/>

Home Assistant sends simple signals → Apple Home turns them into human feedback.

Examples:

- Dishwasher allowed during cheap power → **announcement**
- Washer/Dryer finished → **spoken alert**
- System state changes → **voice + notification**

---

## Summary

HomeKit Bridge is the controlled boundary between:

- **Home Assistant → logic, automation, energy decisions**
- **Apple Home → UI, control, communication**

It ensures the system stays:

- clean  
- understandable  
- secure  
- family-friendly  
