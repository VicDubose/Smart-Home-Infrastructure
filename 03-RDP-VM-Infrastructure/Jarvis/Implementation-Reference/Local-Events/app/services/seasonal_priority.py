from __future__ import annotations

from argparse import ArgumentParser
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.database import connect


TZ = ZoneInfo("America/Chicago")
ROLLING_DAYS = 30
CONFIDENCE_MIN = 70


def now_iso():
    return datetime.now(TZ).isoformat(timespec="seconds")


def quarter_for_month(month):
    return ((month - 1) // 3) + 1


def next_quarter(q):
    return 1 if q == 4 else q + 1


def promote_tier(tier):
    return {
        "T1": "T1",
        "T2": "T1",
        "T3": "T2",
    }.get(tier, tier)


def parse_date(value):
    if not value:
        return None

    text = str(value).strip()

    try:
        return datetime.fromisoformat(
            text.replace("Z", "+00:00")
        ).date()
    except Exception:
        pass

    try:
        return date.fromisoformat(text[:10])
    except Exception:
        return None


def find_date_column(conn):
    columns = {
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(events)"
        )
    }

    for candidate in (
        "start_time",
        "start_datetime",
        "start_date",
        "event_start",
        "date",
    ):
        if candidate in columns:
            return candidate

    raise RuntimeError(
        "No supported event date column found."
    )


def upsert_meta(conn, key, value):
    conn.execute(
        """
        INSERT INTO project_meta (
            key,
            value,
            updated_at
        )
        VALUES (?, ?, ?)
        ON CONFLICT(key)
        DO UPDATE SET
            value = excluded.value,
            updated_at = excluded.updated_at
        """,
        (key, str(value), now_iso()),
    )


def main():
    parser = ArgumentParser()

    parser.add_argument(
        "--as-of",
        help="Override current date YYYY-MM-DD",
    )

    args = parser.parse_args()

    today = (
        date.fromisoformat(args.as_of)
        if args.as_of
        else datetime.now(TZ).date()
    )

    current_q = quarter_for_month(today.month)
    upcoming_q = next_quarter(current_q)
    late_month = today.day >= 16
    window_end = today + timedelta(days=ROLLING_DAYS)

    with connect() as conn:
        date_column = find_date_column(conn)

        rows = conn.execute(
            f"""
            SELECT
                id,
                title,
                {date_column} AS event_date,
                tier,
                seasonal_event,
                seasonal_theme,
                seasonal_confidence
            FROM events
            WHERE canonical = 1
              AND active = 1
            """
        ).fetchall()

        boosted = 0
        seasonal_count = 0

        for row in rows:
            event_date = parse_date(
                row["event_date"]
            )

            event_q = (
                quarter_for_month(event_date.month)
                if event_date
                else None
            )

            seasonal = bool(
                row["seasonal_event"]
            )

            confidence = float(
                row["seasonal_confidence"] or 0
            )

            boost = False
            reason = "geographic"

            if (
                seasonal
                and confidence >= CONFIDENCE_MIN
                and event_date
            ):
                seasonal_count += 1

                if event_q == current_q:
                    boost = True
                    reason = (
                        "current-season:"
                        f"{row['seasonal_theme']}"
                    )

                elif (
                    late_month
                    and event_q == upcoming_q
                    and today <= event_date <= window_end
                ):
                    boost = True
                    reason = (
                        "next-season-lookahead:"
                        f"{row['seasonal_theme']}"
                    )

            priority_tier = (
                promote_tier(row["tier"])
                if boost
                else row["tier"]
            )

            if boost:
                boosted += 1

            conn.execute(
                """
                UPDATE events
                SET
                    season_quarter = ?,
                    season_boost_active = ?,
                    priority_tier = ?,
                    priority_reason = ?,
                    seasonal_updated_at = ?
                WHERE id = ?
                """,
                (
                    event_q,
                    int(boost),
                    priority_tier,
                    reason,
                    now_iso(),
                    row["id"],
                ),
            )

        upsert_meta(
            conn,
            "seasonal_current_quarter",
            f"Q{current_q}",
        )

        upsert_meta(
            conn,
            "seasonal_mode",
            "current_plus_next"
            if late_month
            else "current_only",
        )

        upsert_meta(
            conn,
            "seasonal_boosted_count",
            boosted,
        )

        conn.commit()

    print("===== SEASONAL PRIORITY =====")
    print(f"As of:            {today}")
    print(f"Quarter:          Q{current_q}")
    print(
        "Mode:             "
        + (
            "current + next-quarter lookahead"
            if late_month
            else "current quarter only"
        )
    )
    print(f"Active events:    {len(rows)}")
    print(f"Seasonal events:  {seasonal_count}")
    print(f"Tier promotions:  {boosted}")
    print(f"Date column:      {date_column}")


if __name__ == "__main__":
    main()
