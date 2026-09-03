from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.database import connect


TZ = ZoneInfo(
    "America/Chicago"
)


EVENT_COLUMNS = {
    "seasonal_event":
        "INTEGER DEFAULT 0",

    "seasonal_theme":
        "TEXT",

    "seasonal_confidence":
        "REAL",

    "season_quarter":
        "INTEGER",

    "season_boost_active":
        "INTEGER DEFAULT 0",

    "priority_tier":
        "TEXT",

    "priority_reason":
        "TEXT",

    "seasonal_updated_at":
        "TEXT",

    "score_breakdown":
        "TEXT",

    "scoring_version":
        "TEXT",
}


def now_iso():
    return datetime.now(
        TZ
    ).isoformat(
        timespec="seconds"
    )


def main():

    with connect() as conn:

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        existing = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(events)"
            )
        }

        for (
            name,
            definition,
        ) in EVENT_COLUMNS.items():

            if name in existing:
                print(
                    f"EXISTS: events.{name}"
                )
                continue

            conn.execute(
                f"ALTER TABLE events "
                f"ADD COLUMN {name} "
                f"{definition}"
            )

            print(
                f"ADDED: events.{name}"
            )

        # Until seasonal logic says otherwise,
        # priority tier equals factual geo tier.
        conn.execute(
            """
            UPDATE events
            SET priority_tier = tier
            WHERE priority_tier IS NULL
            """
        )

        conn.execute(
            """
            INSERT INTO project_meta (
                key,
                value,
                updated_at
            )
            VALUES (
                'project_version',
                '1.6.0',
                ?
            )
            ON CONFLICT(key)
            DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (
                now_iso(),
            ),
        )

        conn.commit()

    print()
    print(
        "Local Events schema baseline: "
        "v1.6.0"
    )


if __name__ == "__main__":
    main()
