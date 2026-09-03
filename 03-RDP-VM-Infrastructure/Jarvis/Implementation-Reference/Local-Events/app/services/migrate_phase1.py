from app.services.database import connect


WANTED_COLUMNS = {
    "content_hash": "TEXT",
    "ai_version": "TEXT",
    "raw_json": "TEXT",
}


def main():
    with connect() as conn:
        existing = {
            row["name"]
            for row in conn.execute(
                "PRAGMA table_info(events)"
            )
        }

        for name, column_type in WANTED_COLUMNS.items():
            if name in existing:
                print(f"EXISTS: events.{name}")
                continue

            conn.execute(
                f"ALTER TABLE events "
                f"ADD COLUMN {name} {column_type}"
            )

            print(f"ADDED: events.{name}")

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS
            idx_events_content_hash
            ON events(content_hash)
            """
        )

        conn.commit()


if __name__ == "__main__":
    main()
