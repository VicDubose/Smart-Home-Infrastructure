from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json

import yaml

from app.services.database import connect


ROOT = Path(
    "/mnt/appdata/ha-services/local-events"
)

CONFIG = yaml.safe_load(
    (
        ROOT / "config/scoring-v16.yaml"
    ).read_text(
        encoding="utf-8"
    )
)

VERSION = "1.6.0"


def parse_date(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            str(value).replace(
                "Z",
                "+00:00",
            )
        )
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


def decode_keywords(value):
    if not value:
        return []

    try:
        result = json.loads(value)

        if isinstance(result, list):
            return [
                str(x)
                for x in result
            ]
    except Exception:
        pass

    return []


def main():
    with connect() as conn:
        date_column = find_date_column(conn)

        rows = conn.execute(
            f"""
            SELECT
                id,
                title,
                clean_title,
                description,
                {date_column} AS event_date,
                tier,
                priority_tier,
                season_boost_active,
                primary_category,
                keywords,
                personal_interest,
                free_event
            FROM events
            WHERE canonical = 1
              AND active = 1
              AND ai_processed = 1
            """
        ).fetchall()

        for row in rows:
            interest = float(
                row["personal_interest"] or 0
            )

            personal = round(
                interest * 35 / 100
            )

            category = (
                row["primary_category"] or ""
            )

            category_points = int(
                CONFIG[
                    "category_points"
                ].get(
                    category,
                    0,
                )
            )

            keywords = decode_keywords(
                row["keywords"]
            )

            text = " ".join(
                [
                    row["title"] or "",
                    row["clean_title"] or "",
                    row["description"] or "",
                    " ".join(keywords),
                ]
            ).casefold()

            keyword_points = 0
            matched = []

            for keyword, points in CONFIG[
                "keyword_points"
            ].items():
                if keyword.casefold() in text:
                    keyword_points += int(points)
                    matched.append(keyword)

            keyword_points = min(
                keyword_points,
                15,
            )

            event_dt = parse_date(
                row["event_date"]
            )

            weekend = (
                10
                if (
                    event_dt
                    and event_dt.weekday() >= 5
                )
                else 0
            )

            value = (
                5
                if row["free_event"]
                else 0
            )

            novelty_terms = (
                "festival",
                "expo",
                "tasting",
                "bazaar",
                "convention",
                "premiere",
                "special screening",
                "night market",
                "brunch",
                "vintage",
            )

            novelty_hits = [
                term
                for term in novelty_terms
                if term in text
            ]

            novelty = (
                5
                if len(novelty_hits) >= 2
                else 3
                if novelty_hits
                else 0
            )

            # Reserved until we add a reliable
            # popularity/attendance source.
            popularity = 0

            effective_tier = (
                row["priority_tier"]
                or row["tier"]
            )

            tier_modifier = int(
                CONFIG[
                    "tier_modifiers"
                ].get(
                    effective_tier,
                    0,
                )
            )

            raw = (
                personal
                + category_points
                + keyword_points
                + popularity
                + weekend
                + value
                + novelty
                + tier_modifier
            )

            final = max(
                0,
                min(
                    100,
                    round(raw),
                ),
            )

            breakdown = {
                "personal_interest":
                    personal,
                "category_match":
                    category_points,
                "keyword_match":
                    keyword_points,
                "matched_keywords":
                    matched,
                "popularity":
                    popularity,
                "weekend":
                    weekend,
                "value":
                    value,
                "novelty":
                    novelty,
                "geo_tier":
                    row["tier"],
                "priority_tier":
                    effective_tier,
                "seasonal_boost":
                    bool(
                        row[
                            "season_boost_active"
                        ]
                    ),
                "tier_modifier":
                    tier_modifier,
                "final":
                    final,
            }

            conn.execute(
                """
                UPDATE events
                SET
                    score = ?,
                    score_breakdown = ?,
                    scoring_version = ?
                WHERE id = ?
                """,
                (
                    final,
                    json.dumps(
                        breakdown,
                        sort_keys=True,
                    ),
                    VERSION,
                    row["id"],
                ),
            )

        conn.commit()

    print("===== SCORING V1.6 =====")
    print(f"Events scored: {len(rows)}")
    print(f"Date column:   {date_column}")
    print(f"Version:       {VERSION}")


if __name__ == "__main__":
    main()
