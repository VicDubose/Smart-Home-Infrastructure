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

In this architecture:

- Apple Home (AH) acts as the front-end interface
- Home Assistant (HA) operates as the backend logic engine

This separation allows the system to remain powerful without becoming overwhelming to the user.

---

## Interface Preview

### Apple Home Dashboard (Control Layer)
<img src="../Screenshots/IMG_1317.png" width="200"/>

The main dashboard provides fast access to rooms, cameras, climate, and high-value device controls in a layout that is easy to understand at a glance.

This is where users interact with the system directly — without needing to understand how anything works behind the scenes.

---

### Device & Sensor View (Data Layer)
<img src="../Screenshots/IMG_1318.png" width="200"/>

This layer exposes useful environmental data such as room temperature and humidity without requiring users to interact with backend tools.

It provides awareness without complexity — users can see what’s happening without needing to manage it.

---

### Automation System (Logic Layer)
<img src="../Screenshots/IMG_1321.png" width="200"/>

This view represents the user-facing side of automation.

While all complex logic lives in Home Assistant, Apple Home presents:

- arrival / departure automations  
- schedule-based behaviors  
- simple triggers  

This keeps automation understandable and predictable.

---

### iPad Kiosk Interface (Family Control Layer)
<img src="../Screenshots/IMG_1322.png" width="400"/>

The kiosk is the central interaction point of the home.

It is not just a control panel — it is a household command center designed for:

- shared access  
- quick decisions  
- daily workflow support  
- passive awareness  

---

### Home Access & Permissions (Ecosystem Layer)
<img src="../Screenshots/IMG_1323.png" width="200"/>

Apple Home provides secure, structured access through:

- resident roles  
- permission levels  
- Apple ID-based identity  
- encrypted remote control  

This ensures the system remains both accessible and secure.

---

# iPad Kiosk Mode (Home UI Terminal)

## Overview

This configuration transforms an iPad into a home control terminal that operates as a kiosk when docked and a secure personal device when undocked.

The system is designed to:

- remain always-on while docked  
- automatically enter a restricted kiosk interface at home  
- immediately lock when removed from dock  
- avoid complex or brittle automation logic  
- preserve user control and device security  

---

## Design Philosophy

The system follows a minimal, intention-driven approach:

- Use physical state (power connection) as the primary trigger  
- Avoid automation conflicts and race conditions  
- Keep behavior predictable and human-controlled  
- Do not rely on MDM or forced restrictions  
- Separate usability (kiosk) from security (unlock state)  

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

- Auto-Lock: Never  
- Cover Lock/Unlock: Enabled  
- Low Power Mode enabled for fallback lock behavior  

---

### 2. Focus Mode: Kiosk

- Location-based (Home only)  
- Restricts visible apps and Home Screen pages  
- Supports multi-app kiosk usage  
- Replaces rigid Guided Access  

---

### 3. Automation: Connected to Power

Trigger
- iPad connected to power  

Actions
- Enable Kiosk Focus  
- Return to Home Screen  
- Optional visual cue (wallpaper change)  

Result
- Plugging in at home instantly activates kiosk mode  

---

### 4. Automation: Disconnected from Power

Trigger
- iPad disconnected from power  

Actions
- Disable Kiosk Focus  
- Lock device  

Result
- Undocking restores full security immediately  

---

### 5. Manual Control Model

- No forced locking while docked  
- User-controlled lock behavior  
- No timers or camera-based wake logic  
- Avoids unnecessary automation  

---

### 6. Security Strategy

- Lock enforced only when undocked  
- Sensitive apps protected individually  
- No global forced restrictions during kiosk use  

---

## Kitchen Dashboard Design (Real-World Use)

The kiosk is placed in the kitchen because it serves as the decision center of the home.

It is designed to answer three questions instantly:

1. What is happening in the home?  
2. What needs to be done next?  
3. What can be controlled right now?  

---

### Layer 1 — Household Planning

- AnyList (top widget)  
  - Shared grocery list  
  - Meal prep coordination  
  - Real-time updates across devices  

This eliminates friction in cooking and planning.

---

### Layer 2 — Home Control (Apple Home)

- Climate controls  
- appliance status (washer/dryer)  
- lights and switches  
- security state  

This is the primary interaction layer for all users.

Users control the home without ever touching Home Assistant.

---

### Layer 3 — Awareness

Widgets provide passive awareness:

- Weather → impacts HVAC expectations  
- Calendar → affects presence and timing  
- Energy (Powerwall) → shows cost/usage context  
- Location (Find My) → visual presence confirmation  

This allows the home to be understood at a glance.

---

### Layer 4 — Audio Feedback System

Audio is used as a notification layer due to Apple Home limitations.

Examples:

- Washer finished → sound cue  
- Dryer finished → sound cue  
- Dishwasher optimal start time → notification tone  
- Alerts → audible feedback  

This replaces traditional push-notification dependency with ambient awareness.

---

### Layer 5 — Control Apps (Folder)

The “Home Control” folder provides deeper access when needed:

- Home Assistant → admin-level control  
- Eufy → cameras and security  
- Tesla → vehicle + energy system  
- Alabama Power → utility tracking  
- ASUS Router → network visibility  
- AnyList → food planning  
- Termius → infrastructure access  

This layer separates normal use vs advanced control.

---

## Presence-Based Experience (Brief Overview)

Apple Home provides highly reliable presence detection using:

- iPhone geolocation  
- Home Hub coordination  
- encrypted Apple ecosystem tracking  

This presence state is used to:

- automatically switch home/away modes  
- control Eufy security behavior  
- influence climate readiness  
- drive automation visibility  

Full logic is handled in Home Assistant, but Apple Home provides the human-facing state.

---

## Expanded Kiosk Utility

### Household Planning

- grocery management (AnyList)  
- schedule awareness (Calendar)  
- daily planning (Weather + context)  

---

### Media & Audio

Using AirPlay, audio can be routed across:

- Samsung soundbar (via TV)  
- workstation monitors  
- HomePod minis  
- multiple rooms simultaneously  

This enables full-home audio and notification playback.

---

### Intercom & Communication

HomePods provide:

- intercom between rooms  
- spoken notifications  
- hands-free communication  

This turns the system into a communication layer, not just automation.

---

## Why This Approach Works

- eliminates automation conflicts  
- keeps user experience simple  
- hides backend complexity  
- supports multiple users easily  
- aligns with Apple ecosystem design  
- scales without UI redesign  

---

## Design Goals

- make the home understandable at a glance  
- keep controls simple for all users  
- eliminate need for backend interaction  
- combine awareness + control in one place  
- support voice, touch, and passive interaction  

---

## Final State

- Docked → always-on household control terminal  
- Undocked → secure personal device  
- Away → normal personal use  

---
## Physical Deployment Strategy

The smart home interface is intentionally placed in high-traffic areas to maximize usability.

### Kitchen Placement

- Central location in the home
- Used multiple times per day
- Natural decision-making space (food, planning, schedules)
- Accessible to all household members

The kiosk is positioned to allow:

- quick glanceable information
- immediate control without friction
- shared family interaction

This ensures the system is actually used — not ignored.

### Shark Cleaning Integration (Automated Maintenance Layer)

<img src="../Screenshots/shark_schedule.png" width="250"/>
<img src="../Screenshots/shark_map.png" width="250"/>

The SharkClean system provides automated floor maintenance that integrates into the overall smart home workflow.

Cleaning schedules are configured through the Shark app, allowing the robot to:

- run on consistent daily or weekly schedules  
- automatically clean high-traffic areas such as the kitchen and hallway  
- return to dock without user intervention  

This keeps baseline cleanliness maintained without requiring manual effort.

---

### Behavior & System Role

While Shark operates independently, it fits into the broader system design as a background automation layer.

- runs during low-impact times (morning / away periods)  
- avoids interfering with active household use  
- complements other automations rather than competing with them  

The result is a system where:

- the home stays clean automatically  
- no user interaction is required  
- the feature enhances daily life without adding complexity  

