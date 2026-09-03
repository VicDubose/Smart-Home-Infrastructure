from app.services.database import connect


COLUMNS = {
    "canonical": "INTEGER DEFAULT 1",
    "duplicate_of": "INTEGER",
    "duplicate_reason": "TEXT",
}


def main():
    with connect() as conn:
        existing = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(events)"
            )
        }

        for name, definition in COLUMNS.items():
            if name in existing:
                print(f"EXISTS: events.{name}")
                continue

            conn.execute(
                f"ALTER TABLE events "
                f"ADD COLUMN {name} {definition}"
            )

            print(f"ADDED: events.{name}")

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_events_canonical
            ON events(canonical)
            """
        )

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_events_duplicate_of
            ON events(duplicate_of)
            """
        )

        conn.commit()


if __name__ == "__main__":
    main()
