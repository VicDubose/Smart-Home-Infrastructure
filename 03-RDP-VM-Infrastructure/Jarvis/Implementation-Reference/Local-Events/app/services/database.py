from pathlib import Path
import sqlite3

DB_PATH = Path(
    "/mnt/appdata/ha-services/local-events/data/local_events.db"
)

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    event_key TEXT UNIQUE NOT NULL,

    title TEXT NOT NULL,
    clean_title TEXT,
    description TEXT,

    start_time TEXT NOT NULL,
    end_time TEXT,

    venue TEXT,
    city TEXT,
    state TEXT,

    latitude REAL,
    longitude REAL,
    distance_miles REAL,

    tier TEXT,

    primary_category TEXT,
    secondary_categories TEXT,
    keywords TEXT,

    family_friendly INTEGER DEFAULT 0,
    food_related INTEGER DEFAULT 0,
    free_event INTEGER DEFAULT 0,

    personal_interest REAL DEFAULT 0,
    score INTEGER DEFAULT 0,

    starred INTEGER DEFAULT 0,

    source_name TEXT NOT NULL,
    source_event_id TEXT,
    source_url TEXT,

    ai_processed INTEGER DEFAULT 0,
    ai_confidence REAL,

    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    last_changed TEXT,

    active INTEGER DEFAULT 1
);


CREATE TABLE IF NOT EXISTS event_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    name TEXT UNIQUE NOT NULL,
    enabled INTEGER DEFAULT 1,

    source_type TEXT,
    tier_focus TEXT,

    last_attempt TEXT,
    last_success TEXT,

    status TEXT DEFAULT 'unknown',

    events_seen INTEGER DEFAULT 0,
    new_events INTEGER DEFAULT 0,
    changed_events INTEGER DEFAULT 0,

    failure_count INTEGER DEFAULT 0,
    last_error TEXT
);


CREATE TABLE IF NOT EXISTS ai_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    event_id INTEGER NOT NULL,
    job_type TEXT NOT NULL,

    status TEXT DEFAULT 'pending',

    created_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,

    retries INTEGER DEFAULT 0,

    raw_response TEXT,
    error TEXT,

    FOREIGN KEY(event_id) REFERENCES events(id)
);


CREATE TABLE IF NOT EXISTS collection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    started_at TEXT NOT NULL,
    completed_at TEXT,

    run_type TEXT,

    sources_attempted INTEGER DEFAULT 0,
    sources_successful INTEGER DEFAULT 0,

    events_seen INTEGER DEFAULT 0,
    events_new INTEGER DEFAULT 0,
    events_changed INTEGER DEFAULT 0,

    duplicates_removed INTEGER DEFAULT 0,
    ai_jobs_created INTEGER DEFAULT 0,

    status TEXT
);


CREATE INDEX IF NOT EXISTS idx_events_start
ON events(start_time);

CREATE INDEX IF NOT EXISTS idx_events_tier
ON events(tier);

CREATE INDEX IF NOT EXISTS idx_events_score
ON events(score);

CREATE INDEX IF NOT EXISTS idx_events_active
ON events(active);

CREATE INDEX IF NOT EXISTS idx_ai_jobs_status
ON ai_jobs(status);
"""


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def initialize():
    with connect() as conn:
        conn.executescript(SCHEMA)
        conn.commit()


if __name__ == "__main__":
    initialize()
    print(f"Local Events database ready: {DB_PATH}")
