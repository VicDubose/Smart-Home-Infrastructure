# 🏠 HOME ENERGY POLICY — FINAL SOLAR ARCHITECTURE

Dolomite House — Solar Operational Spec (Final)  
Battery-first, automation-governed residential microgrid design  

---

## 🎯 CORE PRIORITY ORDER

1. Dogs Safety  
2. Human Comfort  
3. Energy Efficiency  
4. Grid Cost Optimization  
5. Battery Preservation  

**Safety overrides cost. Layer 0 always wins.**

---

## 🧱 SYSTEM STRUCTURE — 4.5 ENERGY LAYERS

(See Layers 0 → 2.5 in system documentation)

---

# ⚡ Layer 3 — Energy Optimization (Core System)

## 🎯 Objective

Layer 3 transforms the home into a **self-managed residential microgrid** by controlling:

- When energy is used  
- When energy is stored  
- When energy is deferred  

The goal is not just reducing usage — it is **controlling time**.

---

## ☀️ SYSTEM HARDWARE BASELINE

- Solar: ~5.98 kW DC (east/west split)  
- Battery: Tesla Powerwall 3 — 13.5 kWh usable  
- Home Load Target: ~12–13 kWh/day  
- Rate Plan: Alabama Power RTA (Time-of-Use)  

---

## ⏱️ OFF-GRID TARGET

```
15–17 hours per day off-grid (standard target)
```

Includes:
- Full peak window coverage  
- Majority of normal hours  
- Minimal grid dependence  

---

## ☀️ SUMMER PERFORMANCE MODEL (BIRMINGHAM, AL)

### Assumptions

- ~30 consecutive clear-sky days  
- ~6 kW solar system  
- Daily load ≈ 12 kWh  
- Solar production ≈ 25–30 kWh/day  

---

### 🔋 Battery-Only Runtime

```
13.5 kWh ÷ 12 kWh/day ≈ 1.1 days
```

👉 ~26–28 hours runtime without solar  

---

### ☀️ Solar + Battery Runtime

Daily flow:
1. Solar powers home  
2. Excess charges battery  
3. Battery carries overnight  

---

### 🧠 Result

```
Indefinite off-grid operation during sustained summer sun
```

---

### 🔺 Real-World Limits

- Cloud cover  
- HVAC spikes  
- Overnight drain  

---

### ✅ Practical Expectation

```
22–24 hours off-grid daily (realistic upper range)
```

---

## ❄️ WINTER PERFORMANCE MODEL

- Reduced solar production  
- Peak window shifts to 5 AM – 9 AM  

System becomes:

```
Time-constrained instead of energy-constrained
```

---

## 🔄 BATTERY FILL DAYS (CRITICAL)

Scheduled:
- New Year’s Day  
- Labor Day  
- Thanksgiving  
- Christmas  

---

### Purpose

```
Reset battery state and prevent multi-day energy deficit
```

---

### Behavior

- Home runs on grid intentionally  
- Battery fully recharges  

---

## ⏱️ TIME ENGINE (RTA GOVERNANCE)

- Summer Peak: 1 PM – 7 PM  
- Winter Peak: 5 AM – 9 AM  

---

### Internal Windows

- CHEAP → ~9 PM → 4:45 AM  
- STRICT → Peak windows  
- NORMAL → Everything else  

---

### Strategy

- Battery covers STRICT + most NORMAL  
- Grid used only during CHEAP  
- Early cutoff prevents peak collision  

---

## 🔋 POWERWALL GOVERNANCE

Core question:

```
Should the battery carry the house right now?
```

Battery carries when:
- NOT cheap window  
- NOT storm override  
- NOT fill day  
- Above reserve (~20%)  

---

## 🚗 TESLA MODEL 3 — ENERGY SINK

Tesla acts as:

```
Dynamic solar overflow absorber
```

Charging allowed:
- Cheap window  
- Emergency battery (<10%)  
- Solar surplus (battery full + solar active)  

---

## ☀️ SOLAR UTILIZATION PRIORITY

1. Home load  
2. Battery charging  
3. Tesla (overflow sink)  

---

## ⚡ LOAD SHEDDING STRATEGY

```
Never stack major loads during expensive windows
```

Major loads:
- EV charging  
- Dryer  
- Dishwasher  
- Oven  
- Water heater  
- HVAC spikes  

---

## 📊 DATA VALIDATION & SOURCE OF TRUTH

The system uses two independent data sources:

### 1. Real-Time System Data (Primary Control Layer)
- Tesla Powerwall telemetry (minute-level)
- Home Assistant energy calculations
- Solar production + battery flow

This data drives:
- Automations  
- Load control decisions  
- Battery behavior  

---

### 2. Alabama Power Scraper (Ground Truth Layer)

The Alabama Power scraper provides:

```
Utility-recorded hourly energy usage (billing source of truth)
```

Purpose:
- Validate Home Assistant + Powerwall calculations  
- Detect drift or misreporting  
- Compare:
  - Real-time calculated usage  
  - Utility-billed consumption  

---

### 🧠 Why This Matters

- Prevents blind trust in local telemetry  
- Ensures automation decisions align with actual billing  
- Enables long-term tuning of:
  - Load behavior  
  - Battery strategy  
  - Cost optimization  

---

### 🔁 System Feedback Loop

```
Powerwall (real-time) → HA logic → automation decisions  
           ↓
Alabama Power (hourly) → validation → tuning
```

👉 This creates a **closed-loop energy system**

---

## 🧠 SYSTEM BEHAVIOR (DAILY FLOW)

Morning  
→ Battery finishes discharge  

Midday  
→ Solar powers home + charges battery  

Afternoon  
→ Battery full → Tesla absorbs excess  

Evening  
→ Battery carries home  

Night (CHEAP)  
→ Optional grid use  

---

## 🧠 SYSTEM IDENTITY

This is not a smart home.

```
This is a residential microgrid with time-based energy control.
```

- Solar = generation  
- Powerwall = time-shifting engine  
- Tesla = energy sink  
- Home Assistant = orchestrator  
- Grid = fallback only  

---

## 🧠 FINAL SUMMARY

Layer 3 enables:

- ~17 hours daily off-grid baseline  
- Near full-day off-grid operation in summer  
- Controlled winter performance with reset strategy  
- Verified energy tracking using utility-backed data  
- Intelligent load coordination  

---

## ⚡ ONE-LINE SUMMARY

```
Layer 3 converts solar production into time-controlled independence,
validated against real utility billing data.
```
