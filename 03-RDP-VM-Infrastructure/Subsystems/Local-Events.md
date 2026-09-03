# Local Events Intelligence Board

Owner: Tyrone
Primary area: Dolomite / Birmingham, Alabama
Platform: Home Assistant Green + Python scraping/application services + iPad kiosk

## Purpose

The Local Events Intelligence Board automatically discovers events so weekend and road-trip planning does not require manual searching.

The dashboard should provide a rolling 30-day view, distance-aware prioritization, categories, recommendations, and event details.

## Core pipeline

```text
EVENT SOURCES
      ↓
SCRAPE / API / FETCH
      ↓
NORMALIZE
      ↓
DEDUPE
      ↓
GEOCODE / DISTANCE
      ↓
AI CLASSIFICATION WHEN NEEDED
      ↓
SEASONAL / CATEGORY / PRIORITY SCORING
      ↓
HOME ASSISTANT PUBLISH
      ↓
IPAD DASHBOARD + NOTIFICATIONS
```

## Distance model

The project evolved from named city tiers into deterministic distance-aware ranking.

Primary concepts remain:

- local metro / near-term attendance;
- regional road-trip events;
- far-travel watchlist.

## Categories

Core categories include:

- live music / concerts;
- anime / conventions;
- technology / UAB;
- family / kids;
- food / markets;
- community;
- outdoor activities.

Preferred coverage includes Birmingham-area major venues and outdoor/cultural institutions, while still allowing all relevant events onto the board.

## Seasonal logic

The year is divided into four seasonal quarters.

Events with current/upcoming seasonal relevance receive a one-level priority boost while preserving geographic distance classification.

## Scheduling

The production scheduler is the authority for exact current run times.

The design intent is frequent enough refreshes to surface new events before weekends without wasting compute.

## AI rule

Scraping, normalization, dedupe, geocoding, and deterministic scoring should continue independently of AI availability.

AI classification is a queued stage governed by Jarvis resource/thermal policy.
