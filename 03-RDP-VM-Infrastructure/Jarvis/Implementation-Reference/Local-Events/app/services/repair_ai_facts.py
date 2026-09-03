from datetime import datetime
from zoneinfo import ZoneInfo
import json

from app.services.ai_batch import (
    deterministic_postprocess,
)
from app.services.database import connect
from app.services.event_schema import (
    EventAnalysis,
)


TZ = ZoneInfo(
    "America/Chicago"
)


def now_iso():
    return datetime.now(
        TZ
    ).isoformat(
        timespec="seconds"
    )


def main():
    with connect() as conn:

        rows = conn.execute(
            """
            SELECT
                e.id,
                e.title,
                e.description,
                e.venue,
                e.city,
                e.state,
                e.source_name,

                e.family_friendly,
                e.food_related,
                e.free_event,

                j.raw_response

            FROM events e

            JOIN ai_jobs j
              ON j.event_id = e.id

            WHERE
                e.ai_processed = 1
                AND j.status = 'completed'
                AND j.raw_response IS NOT NULL

            ORDER BY e.id
            """
        ).fetchall()

        changed = 0

        for row in rows:

            analysis = (
                EventAnalysis.model_validate_json(
                    row["raw_response"]
                )
            )

            event = {
                "title":
                    row["title"],

                "description":
                    row["description"],

                "venue":
                    row["venue"],

                "city":
                    row["city"],

                "state":
                    row["state"],

                "source":
                    row["source_name"],
            }

            data = deterministic_postprocess(
                analysis,
                event,
            )

            old_values = (
                int(
                    row["family_friendly"]
                    or 0
                ),
                int(
                    row["food_related"]
                    or 0
                ),
                int(
                    row["free_event"]
                    or 0
                ),
            )

            new_values = (
                int(
                    data[
                        "family_friendly"
                    ]
                ),
                int(
                    data[
                        "food_related"
                    ]
                ),
                int(
                    data[
                        "free_event"
                    ]
                ),
            )

            conn.execute(
                """
                UPDATE events
                SET
                    secondary_categories = ?,
                    keywords = ?,
                    family_friendly = ?,
                    food_related = ?,
                    free_event = ?,
                    ai_updated_at = ?
                WHERE id = ?
                """,
                (
                    json.dumps(
                        data[
                            "secondary_categories"
                        ]
                    ),

                    json.dumps(
                        data[
                            "keywords"
                        ]
                    ),

                    new_values[0],
                    new_values[1],
                    new_values[2],

                    now_iso(),

                    row["id"],
                ),
            )

            if (
                old_values
                != new_values
            ):
                changed += 1

                print(
                    f"#{row['id']} "
                    f"{row['title']}"
                )

                print(
                    "  flags "
                    f"{old_values} -> "
                    f"{new_values}"
                )

        conn.commit()

    print()
    print(
        f"Processed: {len(rows)}"
    )

    print(
        f"Flag corrections: {changed}"
    )


if __name__ == "__main__":
    main()
