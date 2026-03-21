
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
- No kiosk restrictions applied

---

## Configuration Breakdown

### 1. Display Settings

- Auto-Lock: **Never**
  - Prevents sleep during kiosk use
- Cover Lock/Unlock: Enabled
- Low Power Mode:
  - Allows automatic locking when battery is low

---

### 2. Focus Mode: Kiosk

- Location-based (Home only)
- Restricts visible apps and Home Screen pages
- Replaces Guided Access for flexibility
- Supports multi-app kiosk environment

---

### 3. Automation: Connected to Power

**Trigger**
- iPad connected to power

**Actions**
- Enable Kiosk Focus
- Return to Home Screen

**Execution**
- Runs immediately
- No confirmation
- No notifications

**Result**
- Plugging in at home → instant kiosk mode

---

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
- Undocking → immediate lock + security boundary

---

### 5. Manual Control Model

- No forced locking while docked
- User may lock device manually if desired
- No timers, presence checks, or camera-based triggers
- System avoids over-automation

---

### 6. Security Strategy

- Device lock enforced only when undocked
- Sensitive apps protected individually (Touch ID / Face ID)
- No global lock enforcement during kiosk use

---

## Why This Approach Works

- Eliminates automation conflicts and edge cases
- Prevents lock/unlock race conditions
- Maintains consistent and predictable behavior
- Aligns with Apple’s native system design
- Avoids unnecessary complexity
- Scales cleanly without future rework

---

## Final State

- Docked at home → always-on kiosk interface
- Undocked → locked and secure
- Away from home → normal operation

---

## Status

Complete and stable.
