from app.services.database import connect


COLUMNS = {
    "primary_category": "TEXT",
    "secondary_categories": "TEXT",
    "ai_rationale": "TEXT",
    "ai_updated_at": "TEXT",
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

        conn.commit()


if __name__ == "__main__":
    main()
