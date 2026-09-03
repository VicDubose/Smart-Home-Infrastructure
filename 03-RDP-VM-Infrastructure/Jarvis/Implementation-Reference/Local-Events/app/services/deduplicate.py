from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import re

import yaml

from app.services.database import connect


ROOT = Path(
    "/mnt/appdata/ha-services/local-events"
)

SOURCES_PATH = ROOT / "config/sources.yaml"

TZ = ZoneInfo("America/Chicago")

AGGREGATORS = {
    "BHMSTR",
    "Birmingham365",
    "InBirmingham",
}


def now_iso():
    return datetime.now(TZ).isoformat(
        timespec="seconds"
    )


def normalized_title(value):
    value = (value or "").lower()

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value,
    )

    return " ".join(
        value.split()
    )


def normalized_city(value):
    return " ".join(
        (value or "").lower().split()
    )


def load_priorities():
    data = yaml.safe_load(
        SOURCES_PATH.read_text()
    ) or {}

    return {
        source["name"]: int(
            source.get("priority", 0)
        )
        for source in data.get(
            "sources",
            []
        )
    }


def compatible(group):
    sources = {
        row["source_name"]
        for row in group
    }

    # Never collapse duplicate rows produced by
    # the same source here. Those can represent
    # genuinely separate showtimes/sessions.
    if len(sources) < 2:
        return False

    cities = {
        normalized_city(row["city"])
        for row in group
        if row["city"]
    }

    if len(cities) > 1:
        return False

    # Conservative first-pass rule:
    # exact normalized title + same date + same city,
    # with at least one aggregator source.
    return bool(
        sources & AGGREGATORS
    )


def choose_canonical(
    rows,
    priorities,
):
    def key(row):
        return (
            priorities.get(
                row["source_name"],
                0,
            ),
            1 if row["source_url"] else 0,
            len(row["description"] or ""),
            -row["id"],
        )

    return max(
        rows,
        key=key,
    )


def main():
    priorities = load_priorities()

    with connect() as conn:
        conn.execute(
            """
            UPDATE events
            SET
                canonical = 1,
                duplicate_of = NULL,
                duplicate_reason = NULL
            """
        )

        rows = conn.execute(
            """
            SELECT
                id,
                title,
                start_time,
                city,
                venue,
                description,
                source_name,
                source_url
            FROM events
            WHERE active = 1
            ORDER BY start_time, title
            """
        ).fetchall()

        groups = {}

        for row in rows:
            date = (
                row["start_time"][:10]
                if row["start_time"]
                else ""
            )

            key = (
                normalized_title(
                    row["title"]
                ),
                date,
            )

            groups.setdefault(
                key,
                [],
            ).append(row)

        duplicate_count = 0
        duplicate_groups = 0

        print(
            "=" * 76
        )
        print(
            " LOCAL EVENTS — CROSS-SOURCE DEDUPE"
        )
        print(
            "=" * 76
        )

        for key, group in groups.items():
            if len(group) < 2:
                continue

            if not compatible(group):
                continue

            canonical = choose_canonical(
                group,
                priorities,
            )

            duplicates = [
                row
                for row in group
                if row["id"]
                != canonical["id"]
            ]

            if not duplicates:
                continue

            duplicate_groups += 1

            print()
            print(
                f"CANONICAL #{canonical['id']}: "
                f"{canonical['title']}"
            )
            print(
                f"  source: "
                f"{canonical['source_name']}"
            )

            for duplicate in duplicates:
                reason = (
                    "exact-title/date/city "
                    "cross-source duplicate"
                )

                conn.execute(
                    """
                    UPDATE events
                    SET
                        canonical = 0,
                        duplicate_of = ?,
                        duplicate_reason = ?
                    WHERE id = ?
                    """,
                    (
                        canonical["id"],
                        reason,
                        duplicate["id"],
                    ),
                )

                conn.execute(
                    """
                    UPDATE ai_jobs
                    SET
                        status = 'skipped_duplicate',
                        completed_at = ?,
                        error = ?
                    WHERE event_id = ?
                      AND status = 'pending'
                    """,
                    (
                        now_iso(),
                        (
                            "Duplicate of canonical "
                            f"event {canonical['id']}"
                        ),
                        duplicate["id"],
                    ),
                )

                duplicate_count += 1

                print(
                    f"  DUPLICATE "
                    f"#{duplicate['id']} "
                    f"{duplicate['source_name']}"
                )

        conn.commit()

    print()
    print(
        "=" * 76
    )
    print(
        f"Duplicate groups: {duplicate_groups}"
    )
    print(
        f"Rows suppressed:  {duplicate_count}"
    )
    print(
        "=" * 76
    )


if __name__ == "__main__":
    main()
