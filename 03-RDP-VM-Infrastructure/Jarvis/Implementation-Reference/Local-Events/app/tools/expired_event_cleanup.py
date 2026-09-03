#!/usr/bin/env python3

from __future__ import annotations

import argparse
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any


DEFAULT_DB = Path(
    "/mnt/appdata/ha-services/local-events/"
    "data/local_events.db"
)

END_CANDIDATES = (
    "end_datetime",
    "end_time",
    "end_date",
    "event_end",
)

START_CANDIDATES = (
    "start_datetime",
    "start_time",
    "start_date",
    "event_date",
    "date",
    "event_start",
)


def parse_day(value: Any) -> date | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        try:
            stamp = float(value)

            if stamp > 10_000_000_000:
                stamp /= 1000

            return datetime.fromtimestamp(
                stamp
            ).date()
        except (ValueError, OSError, OverflowError):
            return None

    text = str(value).strip()

    if not text:
        return None

    if text.isdigit():
        try:
            stamp = float(text)

            if stamp > 10_000_000_000:
                stamp /= 1000

            return datetime.fromtimestamp(
                stamp
            ).date()
        except (ValueError, OSError, OverflowError):
            pass

    normalized = text.replace(
        "Z",
        "+00:00",
    )

    try:
        parsed = datetime.fromisoformat(
            normalized
        )

        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()

        return parsed.date()

    except ValueError:
        pass

    formats = (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
    )

    for pattern in formats:
        try:
            return datetime.strptime(
                text,
                pattern,
            ).date()
        except ValueError:
            continue

    return None


def chunks(values, size=400):
    for index in range(
        0,
        len(values),
        size,
    ):
        yield values[
            index:index + size
        ]


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_DB,
    )

    parser.add_argument(
        "--execute",
        action="store_true",
    )

    args = parser.parse_args()

    if not args.database.is_file():
        print(
            f"BLOCK: Database missing: "
            f"{args.database}"
        )
        return 2

    conn = sqlite3.connect(
        args.database,
        timeout=30,
    )

    conn.row_factory = sqlite3.Row
    conn.execute(
        "PRAGMA foreign_keys=ON"
    )

    event_columns = {
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(events)"
        )
    }

    job_columns = {
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(ai_jobs)"
        )
    }

    if "id" not in event_columns:
        print(
            "BLOCK: events.id does not exist."
        )
        return 2

    if "event_id" not in job_columns:
        print(
            "BLOCK: ai_jobs.event_id "
            "does not exist."
        )
        return 2

    end_column = next(
        (
            name
            for name in END_CANDIDATES
            if name in event_columns
        ),
        None,
    )

    start_column = next(
        (
            name
            for name in START_CANDIDATES
            if name in event_columns
        ),
        None,
    )

    if (
        end_column is None
        and start_column is None
    ):
        print(
            "BLOCK: No recognized event "
            "date column exists."
        )
        return 2

    selected = ["id"]

    if "title" in event_columns:
        selected.append("title")

    if start_column:
        selected.append(start_column)

    if (
        end_column
        and end_column not in selected
    ):
        selected.append(end_column)

    sql = (
        "SELECT "
        + ", ".join(
            f'"{column}"'
            for column in selected
        )
        + " FROM events"
    )

    today = datetime.now().date()

    expired: list[
        tuple[int, str, date]
    ] = []

    undated = 0
    protected_running = 0

    running_event_ids = {
        row[0]
        for row in conn.execute(
            """
            SELECT DISTINCT event_id
            FROM ai_jobs
            WHERE status='running'
              AND event_id IS NOT NULL
            """
        )
    }

    for row in conn.execute(sql):
        event_id = row["id"]

        title = (
            str(row["title"])
            if "title" in row.keys()
            else ""
        )

        event_day = None

        if end_column:
            event_day = parse_day(
                row[end_column]
            )

        if (
            event_day is None
            and start_column
        ):
            event_day = parse_day(
                row[start_column]
            )

        if event_day is None:
            undated += 1
            continue

        if event_day >= today:
            continue

        if event_id in running_event_ids:
            protected_running += 1
            continue

        expired.append(
            (
                event_id,
                title,
                event_day,
            )
        )

    print(
        "========================================"
    )
    print(
        " LOCAL EVENTS EXPIRED CLEANUP"
    )
    print(
        "========================================"
    )
    print(f"Today:              {today}")
    print(
        f"Start date column:  {start_column}"
    )
    print(
        f"End date column:    {end_column}"
    )
    print(
        f"Expired candidates: {len(expired)}"
    )
    print(
        f"Undated retained:   {undated}"
    )
    print(
        "Running retained:  "
        f"{protected_running}"
    )

    if expired:
        print()
        print(
            "Oldest candidates:"
        )

        for (
            event_id,
            title,
            event_day,
        ) in sorted(
            expired,
            key=lambda item: item[2],
        )[:20]:
            print(
                f"{event_day} | "
                f"{event_id} | "
                f"{title}"
            )

    if not args.execute:
        print()
        print(
            "DRY RUN ONLY — nothing deleted."
        )
        conn.close()
        return 0

    ids = [
        item[0]
        for item in expired
    ]

    if not ids:
        print()
        print(
            "✅ Nothing expired. No changes."
        )
        conn.close()
        return 0

    try:
        conn.execute(
            "BEGIN IMMEDIATE"
        )

        jobs_deleted = 0
        events_deleted = 0

        for group in chunks(ids):
            placeholders = ",".join(
                "?"
                for _ in group
            )

            cursor = conn.execute(
                f"""
                DELETE FROM ai_jobs
                WHERE event_id IN (
                    {placeholders}
                )
                """,
                group,
            )

            jobs_deleted += cursor.rowcount

        for group in chunks(ids):
            placeholders = ",".join(
                "?"
                for _ in group
            )

            cursor = conn.execute(
                f"""
                DELETE FROM events
                WHERE id IN (
                    {placeholders}
                )
                """,
                group,
            )

            events_deleted += cursor.rowcount

        conn.commit()

    except Exception as error:
        conn.rollback()

        print()
        print(
            "❌ Cleanup rolled back."
        )
        print(
            f"Reason: {type(error).__name__}: "
            f"{error}"
        )

        conn.close()
        return 1

    print()
    print(
        f"✅ Events deleted:  {events_deleted}"
    )
    print(
        f"✅ AI jobs deleted: {jobs_deleted}"
    )

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
