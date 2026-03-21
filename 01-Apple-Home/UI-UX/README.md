
# UI / UX

## Overview

The Apple Home UI/UX layer is designed to make the smart home system understandable, accessible, and useful in daily life.

Rather than exposing technical complexity, this layer focuses on:

- glanceable information
- simple room-based controls
- shared household usability
- voice-first interaction
- kiosk-based access for common tasks

The goal is to make a complex backend feel simple on the surface.

---

## Interface Preview

### Apple Home Dashboard (Control Layer)
<img src="../Screenshots/IMG_1317.png" width="200"/>

The main dashboard provides fast access to rooms, cameras, climate, and high-value device controls in a layout that is easy to understand at a glance.

---

### Device & Sensor View (Data Layer)
<img src="../Screenshots/IMG_1318.png" width="200"/>

This layer exposes useful environmental data such as room temperature and humidity without requiring users to interact with backend tools.

---

### Automation System (Logic Layer)
<img src="../Screenshots/IMG_1321.png" width="200"/>

The automation view shows the user-facing side of Apple Home automations, including arrival, departure, and scheduled behavior.

---

### iPad Kiosk Interface (Family Control Layer)
<img src="../Screenshots/IMG_1322.png" width="400"/>

The kiosk acts as a shared smart home terminal for the entire household, combining device control with real-world daily utility.

---

### Home Access & Permissions (Ecosystem Layer)
<img src="../Screenshots/IMG_1323.png" width="200"/>

This screen shows how Apple Home supports shared household access through clear roles, resident permissions, and Apple ecosystem-level security.

---

# iPad Kiosk Mode (Home UI Terminal)

## Overview

This configuration transforms an iPad into a **home control terminal** that operates as a kiosk when docked and a secure personal device when undocked.

The system is designed to:

- remain always-on while docked
- automatically enter a restricted kiosk interface at home
- immediately lock when removed from dock
- avoid complex or brittle automation logic
- preserve user control and device security

---

## Design Philosophy

The system follows a minimal, intention-driven approach:

- Use **physical state (power connection)** as the primary trigger
- Avoid automation conflicts and race conditions
- Keep behavior predictable and human-controlled
- Do not rely on MDM or forced restrictions
- Separate **usability (kiosk)** from **security (unlock state)**

---

## System Behavior

### Docked (Home Mode)

- iPad remains awake
- Kiosk Focus is enabled
- Limited apps and pages are visible
- Device may remain unlocked intentionally

### Undocked (Secure Mode)

- Kiosk Focus is disabled
- Screen locks immediately
- Full device security is restored

### Away From Home

- iPad behaves normally
- No kiosk restrictions are applied

---

## Configuration Breakdown

### 1. Display Settings

- Auto-Lock: **Never**
  - Prevents sleep during kiosk use
- Cover Lock/Unlock: Enabled
- Low Power Mode:
  - allows automatic locking when battery is low

### 2. Focus Mode: Kiosk

- Location-based (Home only)
- Restricts visible apps and Home Screen pages
- Replaces Guided Access for flexibility
- Supports multi-app kiosk use

### 3. Automation: Connected to Power

**Trigger**
- iPad connected to power

**Actions**
- Enable Kiosk Focus
- Return to Home Screen
- Background Changes as visual que

**Execution**
- Runs immediately
- No confirmation
- No notifications

**Result**
- Plugging in at home enters kiosk mode instantly

### 4. Automation: Disconnected from Power

**Trigger**
- iPad disconnected from power

**Actions**
- Disable Kiosk Focus
- Lock device

**Execution**
- Runs immediately
- No confirmation
- No notifications

**Result**
- Undocking immediately restores the security boundary

### 5. Manual Control Model

- No forced locking while docked
- User may lock device manually if desired
- No timers, presence checks, or camera-based wake logic
- System avoids over-automation

### 6. Security Strategy

- Device lock enforced only when undocked
- Sensitive apps protected individually (Touch ID / Face ID)
- No global device-wide lock enforcement during kiosk use

---

## Expanded Kiosk Utility

The kiosk is designed to support more than basic smart home control.

### Household Planning

The interface includes tools such as:

- AnyList for grocery planning and food prep
- calendar widgets for schedule awareness
- weather and contextual day planning
- quick-launch apps for shopping and household planning

This makes the kiosk useful even when no one is directly controlling devices.

### Media & Audio Convenience

The Apple ecosystem makes media routing flexible and simple.

Using AirPlay, audio can be routed across:

- the Samsung soundbar through the den TV
- desk monitors at the workstation
- two HomePod minis
- other Apple audio endpoints in the home

This allows the system to support a broader, house-wide listening experience while keeping control simple.

### Intercom & Communication

HomePods also provide a practical communication layer:

- intercom between rooms
- spoken household notifications
- hands-free communication across the home

This improves usability beyond device control and helps the front-end layer feel like part of the home itself.

---

## Why This Approach Works

- Eliminates automation conflicts and edge cases
- Prevents lock/unlock race conditions
- Maintains consistent and predictable behavior
- Aligns with Apple’s native system design
- Avoids unnecessary complexity
- Scales cleanly without future rework

---

## Design Goals

The UI/UX layer is built around a few core goals:

- make the home understandable at a glance
- keep shared controls simple for family use
- minimize the need for technical interaction
- combine useful household information with device control
- support voice, touch, and kiosk-based interaction equally well

---

## Final State

- Docked at home → always-on kiosk interface
- Undocked → locked and secure
- Away from home → normal operation

---

## Status

Complete and stable.
