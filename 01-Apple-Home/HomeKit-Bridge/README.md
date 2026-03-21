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

<img src="../Screenshots/IMG_1317.png" width="300"/>

This is the real Apple Home interface powered by the HomeKit Bridge.  
Everything visible here is intentionally exposed — nothing more.

---

## Design Philosophy

The bridge follows a strict **allowlist-first approach**:

- expose only useful, human-facing entities
- hide noisy infrastructure entities
- keep Tesla / Powerwall / router telemetry out of Apple Home
- prevent adaptive recovery and HVAC helper noise from cluttering the user interface
- separate security-focused devices from general household controls

This allows Apple Home to stay clean, stable, and understandable.

---

## Bridge Structure

The system is split into multiple bridges to keep behavior organized and stable.

### Bridge 1 — Security + Helpers

This bridge focuses on:

- washer / laundry helper states
- Eufy security entities
- guard mode selection
- current security mode
- Shelly H&T environmental sensors

This makes security and critical state information available in Apple Home without mixing it into the general household UI.

### Bridge 2 — General House UI

This bridge handles the normal family-facing control surface, including:

- lighting
- plugs and switches
- climate entities
- door locks
- camera snapshots
- TVs and media players

This is the bridge that powers most day-to-day Apple Home interaction.

---

## Example: Camera + Access Layer

<img src="../Screenshots/IMG_1323.png" width="200"/>

Camera snapshots, shared access, and household visibility are exposed in a way that is immediately usable without requiring backend knowledge.

---

## Commonly Exposed Entity Types

The most common types of entities exposed into Apple Home are:

- climate entities
- locks
- plugs and switches
- helper booleans
- temperature sensors
- humidity sensors
- water leak sensors
- home base / home-away status
- camera snapshots from activity
- appliance status indicators

These are chosen because they represent things users can understand and act on immediately.

---

## What Is Intentionally Kept Out

The bridge intentionally avoids exposing internal-only logic and noisy backend entities such as:

- adaptive recovery helpers
- HVAC automation internals
- timers and support entities
- router telemetry
- Tesla / Powerwall entities
- backend-only automation states
- technical diagnostic noise

This keeps Apple Home focused on **control and communication**, not implementation detail.

---

## Communication Role

HomeKit Bridge is also used as a **communication path** between Home Assistant and Apple Home.

It carries:

- alert flags
- appliance status updates
- presence-related state
- user-facing climate controls
- helper entities used for Siri-triggered announcements

This supports a clean architectural pattern:

> Home Assistant computes  
> Apple Home communicates

---

## Siri Voice Announcement Pattern

<img src="../Screenshots/IMG_1321.png" width="200"/>

Virtual alert booleans and helper entities are part of the design.

These helpers allow Home Assistant to send simple event states into Apple Home, where Apple devices can turn them into:

- spoken Siri announcements
- user-facing notifications
- household audio cues

Examples include:

- dishwasher availability during low-cost times
- washer and dryer completion alerts
- presence-based status changes
- other human-readable system events

This keeps the experience native to Apple Home while allowing automation logic to stay in the backend.

---

## Summary

HomeKit Bridge acts as the controlled boundary between:

- **Home Assistant** as the automation and orchestration engine
- **Apple Home** as the user interface, communication, and control layer

It is intentionally selective, human-centered, and designed to support real household use rather than expose raw system complexity and its really cool. 
