from __future__ import annotations

from app.collectors.regional_source_pack import (
    REGIONAL_SOURCES,
)

from app.services.database import connect


REGION_LABELS = {
    "huntsville":
        "HUNTSVILLE",

    "mobile":
        "MOBILE",

    "daytona_beach":
        "DAYTONA BEACH",

    "pensacola":
        "PENSACOLA",
}


def main():
    with connect() as conn:

        rows = conn.execute(
            """
            SELECT
                source_name,
                COUNT(*) AS events,
                SUM(
                    canonical = 1
                    AND active = 1
                ) AS active_events
            FROM events
            GROUP BY source_name
            """
        ).fetchall()

        counts = {
            row["source_name"]: {
                "events":
                    row["events"],

                "active":
                    row["active_events"],
            }
            for row in rows
        }

        for region in (
            "huntsville",
            "mobile",
            "daytona_beach",
            "pensacola",
        ):

            print()
            print(
                "=" * 72
            )

            print(
                f" {REGION_LABELS[region]}"
            )

            print(
                "=" * 72
            )

            sources = [
                source
                for source
                in REGIONAL_SOURCES
                if source["region"]
                == region
            ]

            for source in sources:

                result = counts.get(
                    source["name"],
                    {
                        "events": 0,
                        "active": 0,
                    },
                )

                print(
                    f"{source['name']:<42} "
                    f"active="
                    f"{result['active']:<4} "
                    f"role="
                    f"{source['role']}"
                )

        print()
        print(
            "=" * 72
        )

        pending = conn.execute(
            """
            SELECT COUNT(*)
            FROM ai_jobs
            WHERE status = 'pending'
            """
        ).fetchone()[0]

        active = conn.execute(
            """
            SELECT COUNT(*)
            FROM events
            WHERE canonical = 1
              AND active = 1
            """
        ).fetchone()[0]

        print(
            f"Active canonical events: "
            f"{active}"
        )

        print(
            f"Pending AI jobs: "
            f"{pending}"
        )

        print(
            "=" * 72
        )


if __name__ == "__main__":
    main()
