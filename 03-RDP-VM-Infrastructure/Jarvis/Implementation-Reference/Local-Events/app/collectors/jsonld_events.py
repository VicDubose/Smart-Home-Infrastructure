from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import json

import requests
from bs4 import BeautifulSoup

from app.services.database import connect
from app.services.normalize import (
    normalize_jsonld_event,
    parse_datetime,
)
from app.services.source_registry import get_source


TZ = ZoneInfo("America/Chicago")

ROOT = Path(
    "/mnt/appdata/ha-services/local-events"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/126 Safari/537.36 "
        "LocalEventsIntelligenceBoard/1.0"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def now():
    return datetime.now(TZ)


def now_iso():
    return now().isoformat(
        timespec="seconds"
    )


def walk_json(node):
    if isinstance(node, dict):
        yield node

        for value in node.values():
            yield from walk_json(value)

    elif isinstance(node, list):
        for value in node:
            yield from walk_json(value)


def is_event_type(value):
    if isinstance(value, str):
        return value.lower() == "event"

    if isinstance(value, list):
        return any(
            isinstance(item, str)
            and item.lower() == "event"
            for item in value
        )

    return False


def extract_jsonld(html):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    found = []

    for script in soup.find_all(
        "script",
        attrs={
            "type": "application/ld+json"
        },
    ):
        raw = (
            script.string
            or script.get_text()
        )

        if not raw:
            continue

        try:
            payload = json.loads(raw)
        except Exception:
            continue

        for item in walk_json(payload):
            if is_event_type(
                item.get("@type")
            ):
                found.append(item)

    return found


def within_window(record, days=30):
    start = parse_datetime(
        record["start_time"]
    )

    if not start:
        return False

    lower = now() - timedelta(
        hours=12
    )

    upper = now() + timedelta(
        days=days
    )

    return lower <= start <= upper


def queue_ai_job(
    conn,
    event_id,
):
    exists = conn.execute(
        """
        SELECT 1
        FROM ai_jobs
        WHERE event_id = ?
          AND job_type = 'classify_event'
          AND status IN ('pending', 'running')
        LIMIT 1
        """,
        (event_id,),
    ).fetchone()

    if exists:
        return False

    conn.execute(
        """
        INSERT INTO ai_jobs (
            event_id,
            job_type,
            status,
            created_at
        )
        VALUES (?, ?, 'pending', ?)
        """,
        (
            event_id,
            "classify_event",
            now_iso(),
        ),
    )

    return True


def upsert_event(
    conn,
    record,
):
    existing = conn.execute(
        """
        SELECT
            id,
            content_hash
        FROM events
        WHERE event_key = ?
        """,
        (
            record["event_key"],
        ),
    ).fetchone()

    timestamp = now_iso()

    if existing is None:
        cursor = conn.execute(
            """
            INSERT INTO events (
                event_key,
                title,
                description,
                start_time,
                end_time,
                venue,
                city,
                state,
                latitude,
                longitude,
                source_name,
                source_event_id,
                source_url,
                content_hash,
                raw_json,
                ai_processed,
                first_seen,
                last_seen,
                last_changed,
                active
            )
            VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, 0, ?, ?, ?,
                1
            )
            """,
            (
                record["event_key"],
                record["title"],
                record["description"],
                record["start_time"],
                record["end_time"],
                record["venue"],
                record["city"],
                record["state"],
                record["latitude"],
                record["longitude"],
                record["source_name"],
                record["source_event_id"],
                record["source_url"],
                record["content_hash"],
                record["raw_json"],
                timestamp,
                timestamp,
                timestamp,
            ),
        )

        event_id = cursor.lastrowid

        queued = queue_ai_job(
            conn,
            event_id,
        )

        return (
            "new",
            queued,
        )

    changed = (
        existing["content_hash"]
        != record["content_hash"]
    )

    if changed:
        conn.execute(
            """
            UPDATE events
            SET
                title = ?,
                description = ?,
                start_time = ?,
                end_time = ?,
                venue = ?,
                city = ?,
                state = ?,
                latitude = ?,
                longitude = ?,
                source_name = ?,
                source_event_id = ?,
                source_url = ?,
                content_hash = ?,
                raw_json = ?,
                ai_processed = 0,
                last_seen = ?,
                last_changed = ?,
                active = 1
            WHERE id = ?
            """,
            (
                record["title"],
                record["description"],
                record["start_time"],
                record["end_time"],
                record["venue"],
                record["city"],
                record["state"],
                record["latitude"],
                record["longitude"],
                record["source_name"],
                record["source_event_id"],
                record["source_url"],
                record["content_hash"],
                record["raw_json"],
                timestamp,
                timestamp,
                existing["id"],
            ),
        )

        queued = queue_ai_job(
            conn,
            existing["id"],
        )

        return (
            "changed",
            queued,
        )

    conn.execute(
        """
        UPDATE events
        SET
            last_seen = ?,
            active = 1
        WHERE id = ?
        """,
        (
            timestamp,
            existing["id"],
        ),
    )

    return (
        "unchanged",
        False,
    )


def collect_source(
    source_id,
    commit=True,
):
    source = get_source(
        source_id
    )

    session = requests.Session()
    session.headers.update(
        HEADERS
    )

    response = session.get(
        source["url"],
        timeout=(7, 30),
    )

    response.raise_for_status()

    raw_events = extract_jsonld(
        response.text
    )

    normalized = []

    for item in raw_events:
        record = normalize_jsonld_event(
            source,
            item,
        )

        if not record:
            continue

        if not within_window(
            record,
            days=30,
        ):
            continue

        normalized.append(
            record
        )

    stats = {
        "source": source["name"],
        "raw": len(raw_events),
        "eligible": len(normalized),
        "new": 0,
        "changed": 0,
        "unchanged": 0,
        "ai_jobs": 0,
    }

    if not commit:
        return stats, normalized

    with connect() as conn:
        for record in normalized:
            state, queued = upsert_event(
                conn,
                record,
            )

            stats[state] += 1

            if queued:
                stats["ai_jobs"] += 1

        conn.execute(
            """
            UPDATE event_sources
            SET
                events_seen = ?,
                new_events = ?,
                changed_events = ?,
                last_success = ?,
                status = 'online',
                failure_count = 0,
                last_error = NULL
            WHERE name = ?
            """,
            (
                stats["eligible"],
                stats["new"],
                stats["changed"],
                now_iso(),
                source["name"],
            ),
        )

        conn.commit()

    return stats, normalized


def main():
    source_ids = [
        "bjcc",
        "uab",
        "bhmstr",
    ]

    print("=" * 78)
    print(
        " LOCAL EVENTS — STRUCTURED "
        "JSON-LD COLLECTION"
    )
    print("=" * 78)

    totals = {
        "raw": 0,
        "eligible": 0,
        "new": 0,
        "changed": 0,
        "unchanged": 0,
        "ai_jobs": 0,
    }

    for source_id in source_ids:
        stats, _ = collect_source(
            source_id,
            commit=True,
        )

        print()
        print(stats["source"])
        print(
            f"  Raw JSON-LD:      "
            f"{stats['raw']}"
        )
        print(
            f"  30-day eligible:  "
            f"{stats['eligible']}"
        )
        print(
            f"  New:              "
            f"{stats['new']}"
        )
        print(
            f"  Changed:          "
            f"{stats['changed']}"
        )
        print(
            f"  Unchanged:        "
            f"{stats['unchanged']}"
        )
        print(
            f"  AI jobs queued:   "
            f"{stats['ai_jobs']}"
        )

        for key in totals:
            totals[key] += stats[key]

    print()
    print("=" * 78)
    print(" COLLECTION TOTAL")
    print("=" * 78)

    for key, value in totals.items():
        print(
            f"{key:12} {value}"
        )

    print("=" * 78)


if __name__ == "__main__":
    main()
