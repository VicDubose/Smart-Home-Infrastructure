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
# Apple Home Alert Pattern

## Overview

Because Apple Home has limitations around direct custom voice generation, the system uses **Apple-side audio and music cues** as the primary alert mechanism instead of relying on full Siri text-to-speech for every event.

This creates a practical front-end communication layer while keeping automation logic in Home Assistant.

---

## Core Pattern

The system follows this flow:

**Home Assistant → helper flag → HomeKit Bridge → Apple Home automation → audio cue / Apple-side feedback**

This allows backend events to be translated into household-facing signals without requiring users to open Home Assistant.

---

## Why Audio Cues Are Used

Apple Home is excellent for:

- secure device control
- presence-based automations
- HomePod-based interaction
- remote access
- front-end notifications

However, for highly customized spoken alerts, Apple’s behavior can be restrictive.

As a result, the system uses:

- music cues
- tone-based feedback
- Apple-side automation responses
- user-recognizable audio patterns

This keeps notifications reliable and native to the Apple ecosystem.

---

## Example Alert Types

### Laundry Finished
When the washer state changes from running to stopped and remains stopped, Home Assistant raises an alert helper. Apple Home can then trigger an audio cue to let users know the cycle is complete.

### Water Leak Alert
When a leak sensor changes from dry to wet, Home Assistant sets a water leak flag. Apple Home can react to that state and surface the event through front-end notification behavior.

### Dishwasher Availability / Cheap-Time Use
When the dishwasher becomes eligible to run during low-cost time windows, Apple Home can play a cue to indicate that the preferred operating window is active.

---

## Example HA-Side Trigger Types

These are the kinds of helpers that feed into the Apple Home layer:

- `input_boolean.washingmachine_status`
- `binary_sensor.laundry_is_washed`
- `input_boolean.water_leak_status`
- `input_boolean.ah_alert_washer_finished_urgent`

The helper is not the final notification itself.  
It is the **bridge signal** that Apple Home uses to trigger a user-facing response.

---

## Automation Design Principle

Home Assistant performs the detection:

- state change detection
- timing validation
- device-state interpretation
- alert gating

Apple Home performs the human-facing reaction:

- audio cue
- household feedback
- simplified visibility
- user interaction

---

## Why This Split Works

This design keeps the architecture clean:

- **Home Assistant** handles automation logic
- **HomeKit Bridge** carries the signal
- **Apple Home** handles household-facing communication

This avoids overloading Apple Home with backend complexity while still making the home feel responsive and interactive.

---

## Practical Outcome

Even when full spoken Siri announcements are limited, the Apple layer still provides meaningful feedback through:

- music cues
- audio notifications
- HomePod response behavior
- native front-end awareness

The result is a system that still feels alive and communicative without depending on custom backend dashboards.

## Summary

HomeKit Bridge acts as the controlled boundary between:

- **Home Assistant** as the automation and orchestration engine
- **Apple Home** as the user interface, communication, and control layer

It is intentionally selective, human-centered, and designed to support real household use rather than expose raw system complexity and its really cool. 
