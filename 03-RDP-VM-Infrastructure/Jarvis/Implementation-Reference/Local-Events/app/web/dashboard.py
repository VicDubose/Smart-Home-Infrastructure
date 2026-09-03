from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from flask import (
    Flask,
    jsonify,
    render_template,
)

from app.services.database import connect


TZ = ZoneInfo("America/Chicago")

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static",
)


CATEGORY_META = {
    "music":      ("♪",  "Music"),
    "anime":      ("✦",  "Anime"),
    "technology": ("▣",  "Tech"),
    "family":     ("♟",  "Family"),
    "food":       ("♨",  "Food"),
    "community":  ("●",  "Community"),
    "sports":     ("★",  "Sports"),
    "film":       ("▤",  "Film"),
    "arts":       ("✦",  "Arts"),
    "education":  ("◆",  "Education"),
    "health":     ("✚",  "Health"),
    "outdoors":   ("♣",  "Outdoors"),
    "nightlife":  ("☾",  "Nightlife"),
}

# The browser reaches MidCity successfully,
# but its Time.ly tag is not yielding event rows yet.
DEGRADED_SOURCES = {
    "MidCity District",
}


def row_value(row, key, default=None):
    try:
        if key in row.keys():
            value = row[key]

            if value is not None:
                return value

    except Exception:
        pass

    return default


def parse_datetime(value):
    if not value:
        return None

    try:
        dt = datetime.fromisoformat(
            str(value).replace(
                "Z",
                "+00:00",
            )
        )

        if dt.tzinfo is not None:
            dt = dt.astimezone(TZ)

        return dt

    except Exception:
        return None


def format_when(value):
    dt = parse_datetime(value)

    if dt is None:
        return "ANYTIME"

    return dt.strftime(
        "%a, %b %-d|%-I:%M %p"
    )


def clean_display_title(row):
    title = (
        row_value(row, "clean_title")
        or row_value(row, "title")
        or "Untitled Event"
    )

    source = str(
        row_value(
            row,
            "source_name",
            "",
        )
        or ""
    ).strip()

    venue = str(
        row_value(
            row,
            "venue",
            "",
        )
        or ""
    ).strip()

    city = str(
        row_value(
            row,
            "city",
            "",
        )
        or ""
    ).strip()

    state = str(
        row_value(
            row,
            "state",
            "",
        )
        or ""
    ).strip()

    suffixes = [
        f" by {source}",
        f" - {source}",
        f" at {venue} in {city}, {state}",
        f" at {venue} in {city}",
        f" in {city}, {state}",
    ]

    for suffix in suffixes:
        if (
            suffix.strip()
            and title.lower().endswith(
                suffix.lower()
            )
        ):
            title = title[
                : -len(suffix)
            ].rstrip(" -")

    return title


def event_dict(row):
    category = str(
        row_value(
            row,
            "primary_category",
            "",
        )
        or ""
    ).lower()

    icon, category_label = (
        CATEGORY_META.get(
            category,
            ("◆", "Pending"),
        )
    )

    score = row_value(
        row,
        "score",
    )

    if score is not None:
        try:
            score = int(
                round(float(score))
            )
        except Exception:
            score = None

    tier = row_value(
        row,
        "tier",
        "—",
    )

    when = format_when(
        row_value(
            row,
            "start_time",
        )
    )

    when_parts = when.split(
        "|",
        1,
    )

    city = str(
        row_value(
            row,
            "city",
            "",
        )
        or ""
    )

    state = str(
        row_value(
            row,
            "state",
            "",
        )
        or ""
    )

    venue = str(
        row_value(
            row,
            "venue",
            "",
        )
        or ""
    )

    distance = row_value(
        row,
        "distance_miles",
    )

    if distance is not None:
        try:
            distance = round(
                float(distance),
                1,
            )
        except Exception:
            distance = None

    return {
        "id":
            row_value(row, "id"),

        "title":
            clean_display_title(row),

        "date":
            when_parts[0],

        "time":
            (
                when_parts[1]
                if len(when_parts) > 1
                else ""
            ),

        "city":
            city,

        "state":
            state,

        "venue":
            venue,

        "tier":
            tier,

        "category":
            category or "pending",

        "category_label":
            category_label,

        "icon":
            icon,

        "score":
            score,

        "distance":
            distance,

        "source":
            row_value(
                row,
                "source_name",
                "",
            ),

        "url":
            (
                row_value(
                    row,
                    "source_url",
                )
                or row_value(
                    row,
                    "event_url",
                )
                or row_value(
                    row,
                    "url",
                )
            ),
    }


def fetch_events(conn):
    return conn.execute(
        """
        SELECT *
        FROM events
        WHERE canonical = 1
          AND active = 1
          AND distance_miles IS NOT NULL

          -- QUALITY_FILTER_V17
          AND lower(trim(title)) NOT IN (
              'skip navigation',
              'skip to main content',
              'click here',
              'learn more',
              'read more',
              'view more',
              'more info',
              'get tickets',
              'buy tickets',
              'find events',
              'search',
              'events',
              'event',
              'calendar',
              'event calendar',
              'today',
              'previous events',
              'next events',
              'menu close',
              'home',
              'directions',
              'sign up',
              'subscribe'
          )

          AND lower(trim(title))
              NOT LIKE 'skip navigation%'

          AND lower(trim(title))
              NOT LIKE 'skip to main%'

          AND lower(trim(title))
              NOT LIKE 'private event%'

          AND lower(trim(title))
              NOT LIKE 'cancelled:%'

          AND lower(trim(title))
              NOT LIKE 'canceled:%'

          AND NOT (
              source_name = 'Bands on the Beach'
              AND start_time IS NOT NULL
              AND CAST(
                  strftime(
                      '%w',
                      start_time
                  )
                  AS INTEGER
              ) != 2
          )
          AND (
                start_time IS NULL
                OR date(start_time)
                   BETWEEN date(
                       'now',
                       'localtime'
                   )
                   AND date(
                       'now',
                       'localtime',
                       '+30 days'
                   )
              )
        ORDER BY
            CASE
                WHEN score IS NULL
                    THEN 1
                ELSE 0
            END,
            score DESC,
            start_time ASC,
            distance_miles ASC
        """
    ).fetchall()


def source_health(conn):
    configured = set()

    try:
        rows = conn.execute(
            """
            SELECT
                name,
                active
            FROM event_sources
            """
        ).fetchall()

        for row in rows:
            if row["active"]:
                configured.add(
                    row["name"]
                )

    except Exception:
        pass

    try:
        from app.collectors.regional_source_pack import (
            REGIONAL_SOURCES,
        )

        configured.update(
            source["name"]
            for source
            in REGIONAL_SOURCES
        )

    except Exception:
        pass

    if not configured:
        configured.update(
            row["source_name"]
            for row in conn.execute(
                """
                SELECT DISTINCT source_name
                FROM events
                WHERE source_name IS NOT NULL
                """
            )
        )

    degraded = (
        DEGRADED_SOURCES
        & configured
    )

    total = len(configured)

    return {
        "configured":
            total,

        "healthy":
            max(
                0,
                total - len(degraded),
            ),

        "failed":
            len(degraded),

        "degraded_names":
            sorted(degraded),
    }


def board_data():
    with connect() as conn:

        rows = fetch_events(conn)

        events = [
            event_dict(row)
            for row in rows
        ]

        panels = {
            "T1": [
                event
                for event in events
                if event["tier"] == "T1"
            ],

            "T2": [
                event
                for event in events
                if event["tier"] == "T2"
            ],

            "T3": [
                event
                for event in events
                if event["tier"] == "T3"
            ],
        }

        scored = [
            event
            for event in events
            if event["score"]
            is not None
        ]

        top_picks = sorted(
            scored,
            key=lambda event: (
                -event["score"],
                event["distance"]
                if event["distance"]
                is not None
                else 9999,
            ),
        )[:5]

        score_values = [
            event["score"]
            for event in scored
        ]

        average_score = (
            round(
                sum(score_values)
                / len(score_values)
            )
            if score_values
            else 0
        )

        duplicates = conn.execute(
            """
            SELECT COUNT(*)
            FROM events
            WHERE canonical = 0
              AND duplicate_of
                  IS NOT NULL
            """
        ).fetchone()[0]

        new_today = conn.execute(
            """
            SELECT COUNT(*)
            FROM events
            WHERE canonical = 1
              AND active = 1
              AND date(first_seen)
                  = date(
                      'now',
                      'localtime'
                  )
            """
        ).fetchone()[0]

        pending_ai = conn.execute(
            """
            SELECT COUNT(*)
            FROM ai_jobs
            WHERE status = 'pending'
            """
        ).fetchone()[0]

        last_seen = conn.execute(
            """
            SELECT MAX(last_seen)
            FROM events
            WHERE canonical = 1
              AND active = 1
            """
        ).fetchone()[0]

        source_status = (
            source_health(conn)
        )

    last_dt = parse_datetime(
        last_seen
    )

    last_updated = (
        last_dt.strftime(
            "%b %-d, %Y  %-I:%M %p %Z"
        )
        if last_dt
        else datetime.now(TZ).strftime(
            "%b %-d, %Y  %-I:%M %p %Z"
        )
    )

    stats = {
        "total":
            len(events),

        "t1":
            len(panels["T1"]),

        "t2":
            len(panels["T2"]),

        "t3":
            len(panels["T3"]),

        "duplicates":
            duplicates,

        "new_today":
            new_today,

        "pending_ai":
            pending_ai,

        "average_score":
            average_score,

        "last_updated":
            last_updated,
    }

    return {
        "events":
            events,

        "panels":
            panels,

        "top_picks":
            top_picks,

        "stats":
            stats,

        "sources":
            source_status,
    }


@app.route("/")
def dashboard():
    data = board_data()

    return render_template(
        "dashboard.html",
        **data,
    )


@app.route("/api/stats")
def api_stats():
    data = board_data()

    return jsonify(
        {
            "stats":
                data["stats"],

            "sources":
                data["sources"],
        }
    )


@app.route("/api/events")
def api_events():
    data = board_data()

    return jsonify(
        data["events"]
    )


@app.route("/health")
def health():
    return jsonify(
        {
            "status": "ok",
            "service":
                "local-events-dashboard",
        }
    )


@app.route("/favicon.ico")
def favicon():
    return (
        "",
        204,
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=8787,
        debug=False,
    )
