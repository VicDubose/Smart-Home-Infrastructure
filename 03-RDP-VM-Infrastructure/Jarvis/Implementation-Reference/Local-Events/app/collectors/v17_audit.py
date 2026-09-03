from __future__ import annotations

from app.services.database import connect


SOURCES = (
    "Birmingham Zoo",
    "Birmingham Botanical Gardens",
    "Railroad Park",
    "Alabama Symphony Orchestra",
    "Saturn Birmingham",
    "Avondale Brewing Company",
    "Iron City Birmingham",
    "Dollywood Festivals & Events",
    "Bands on the Beach",
)


def main():

    with connect() as conn:

        print(
            "=" * 80
        )

        print(
            " LOCAL EVENTS V1.7 — SOURCE / QUALITY AUDIT"
        )

        print(
            "=" * 80
        )

        for source in SOURCES:

            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    SUM(
                        CASE
                        WHEN active = 1
                         AND canonical = 1
                        THEN 1
                        ELSE 0
                        END
                    ) AS active
                FROM events
                WHERE source_name = ?
                """,
                (
                    source,
                ),
            ).fetchone()

            print(
                f"{source:<40} "
                f"total={row['total'] or 0:<4} "
                f"active={row['active'] or 0:<4}"
            )

        print()
        print(
            "KNOWN UI-TITLE CANDIDATES"
        )

        print(
            "-" * 80
        )

        rows = conn.execute(
            """
            SELECT
                id,
                source_name,
                title,
                start_time
            FROM events
            WHERE lower(trim(title)) IN (
                'skip navigation',
                'skip to main content',
                'click here',
                'learn more',
                'read more',
                'view more',
                'more info',
                'get tickets',
                'buy tickets'
            )
            OR lower(trim(title))
                LIKE 'skip navigation%'
            OR lower(trim(title))
                LIKE 'skip to main%'
            ORDER BY id
            """
        ).fetchall()

        if not rows:
            print(
                "None"
            )
        else:
            for row in rows:
                print(
                    f"#{row['id']} | "
                    f"{row['source_name']} | "
                    f"{row['title']} | "
                    f"{row['start_time']}"
                )

        print()
        print(
            "=" * 80
        )


if __name__ == "__main__":
    main()
