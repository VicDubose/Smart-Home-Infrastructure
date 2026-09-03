from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import re
import time

import requests

from app.services.database import connect


ROOT = Path(
    "/mnt/appdata/ha-services/local-events"
)

CACHE_FILE = (
    ROOT
    / "cache/venues/reverse-geocode-cache.json"
)

TZ = ZoneInfo(
    "America/Chicago"
)

REVERSE_URL = (
    "https://nominatim.openstreetmap.org/reverse"
)

HEADERS = {
    "User-Agent": (
        "LocalEventsIntelligenceBoard/1.0 "
        "private-home-assistant-dashboard"
    ),
}

STATE_MAP = {
    "Alabama": "AL",
    "Alaska": "AK",
    "Arizona": "AZ",
    "Arkansas": "AR",
    "California": "CA",
    "Colorado": "CO",
    "Connecticut": "CT",
    "Delaware": "DE",
    "Florida": "FL",
    "Georgia": "GA",
    "Hawaii": "HI",
    "Idaho": "ID",
    "Illinois": "IL",
    "Indiana": "IN",
    "Iowa": "IA",
    "Kansas": "KS",
    "Kentucky": "KY",
    "Louisiana": "LA",
    "Maine": "ME",
    "Maryland": "MD",
    "Massachusetts": "MA",
    "Michigan": "MI",
    "Minnesota": "MN",
    "Mississippi": "MS",
    "Missouri": "MO",
    "Montana": "MT",
    "Nebraska": "NE",
    "Nevada": "NV",
    "New Hampshire": "NH",
    "New Jersey": "NJ",
    "New Mexico": "NM",
    "New York": "NY",
    "North Carolina": "NC",
    "North Dakota": "ND",
    "Ohio": "OH",
    "Oklahoma": "OK",
    "Oregon": "OR",
    "Pennsylvania": "PA",
    "Rhode Island": "RI",
    "South Carolina": "SC",
    "South Dakota": "SD",
    "Tennessee": "TN",
    "Texas": "TX",
    "Utah": "UT",
    "Vermont": "VT",
    "Virginia": "VA",
    "Washington": "WA",
    "West Virginia": "WV",
    "Wisconsin": "WI",
    "Wyoming": "WY",
}


def now_iso():
    return datetime.now(
        TZ
    ).isoformat(
        timespec="seconds"
    )


def load_cache():
    if not CACHE_FILE.exists():
        return {}

    try:
        return json.loads(
            CACHE_FILE.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return {}


def save_cache(cache):
    CACHE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    CACHE_FILE.write_text(
        json.dumps(
            cache,
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def state_abbreviation(address):
    iso = (
        address.get("ISO3166-2-lvl4")
        or address.get("ISO3166-2-lvl6")
        or ""
    )

    if iso.startswith("US-"):
        return iso.split(
            "-",
            1,
        )[1].upper()

    state = address.get(
        "state"
    )

    return STATE_MAP.get(
        state,
        state,
    )


def locality(address):
    for key in (
        "city",
        "town",
        "village",
        "municipality",
        "hamlet",
    ):
        value = address.get(
            key
        )

        if value:
            return str(
                value
            ).strip()

    return None


def reverse_lookup(
    session,
    latitude,
    longitude,
):
    response = session.get(
        REVERSE_URL,
        params={
            "lat": latitude,
            "lon": longitude,
            "format": "jsonv2",
            "addressdetails": 1,
        },
        timeout=20,
    )

    response.raise_for_status()

    return response.json()


def normalize(value):
    return re.sub(
        r"\s+",
        " ",
        (value or "").casefold(),
    ).strip()


def main():
    cache = load_cache()

    session = requests.Session()
    session.headers.update(
        HEADERS
    )

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                title,
                city,
                state,
                venue,
                latitude,
                longitude,
                distance_miles
            FROM events
            WHERE canonical = 1
              AND active = 1
              AND latitude IS NOT NULL
              AND longitude IS NOT NULL
              AND geocode_provider IS NULL
              AND distance_miles > 40
            ORDER BY distance_miles
            """
        ).fetchall()

        repaired = 0
        rejected = 0
        review = 0

        print("=" * 78)
        print(" LOCAL EVENTS — SOURCE COORDINATE SANITY CHECK")
        print("=" * 78)

        for row in rows:
            key = (
                f"{float(row['latitude']):.6f},"
                f"{float(row['longitude']):.6f}"
            )

            if key in cache:
                result = cache[key]

            else:
                print(
                    f"REVERSE #{row['id']:03}: "
                    f"{key}"
                )

                try:
                    result = reverse_lookup(
                        session,
                        row["latitude"],
                        row["longitude"],
                    )

                except Exception as exc:
                    print(
                        f"  ERROR: {exc}"
                    )

                    result = None

                cache[key] = result

                save_cache(
                    cache
                )

                time.sleep(
                    1.15
                )

            if not result:
                conn.execute(
                    """
                    UPDATE events
                    SET
                        geo_validation_status = 'review',
                        geo_validation_reason = ?
                    WHERE id = ?
                    """,
                    (
                        "Reverse geocoding failed.",
                        row["id"],
                    ),
                )

                review += 1
                continue

            address = (
                result.get("address")
                or {}
            )

            reverse_city = locality(
                address
            )

            reverse_state = state_abbreviation(
                address
            )

            display_name = result.get(
                "display_name"
            )

            context = normalize(
                " ".join(
                    [
                        row["title"] or "",
                        row["venue"] or "",
                    ]
                )
            )

            city_in_context = (
                reverse_city
                and normalize(
                    reverse_city
                ) in context
            )

            state_conflict = (
                reverse_state
                and row["state"]
                and normalize(
                    reverse_state
                ) != normalize(
                    row["state"]
                )
            )

            print()
            print(
                f"#{row['id']} "
                f"{row['title']}"
            )

            print(
                f"  stored:   "
                f"{row['city']}, {row['state']}"
            )

            print(
                f"  reverse:  "
                f"{reverse_city}, {reverse_state}"
            )

            # Case A:
            # Coordinate clearly points to a place explicitly
            # named by the event itself. Keep coordinate and
            # repair fallback city metadata.
            if (
                reverse_city
                and city_in_context
                and not state_conflict
            ):
                conn.execute(
                    """
                    UPDATE events
                    SET
                        city = ?,
                        state = COALESCE(?, state),
                        geo_validation_status =
                            'repaired_city',
                        geo_validation_reason = ?,
                        reverse_geocode_name = ?
                    WHERE id = ?
                    """,
                    (
                        reverse_city,
                        reverse_state,
                        (
                            "Source coordinates agree with "
                            "a locality named in event/venue; "
                            "fallback city repaired."
                        ),
                        display_name,
                        row["id"],
                    ),
                )

                repaired += 1

                print(
                    "  ACTION: KEEP coordinates; "
                    "repair city."
                )

                continue

            # Case B:
            # Coordinates land in another state.
            # Source coordinate is not trustworthy.
            if state_conflict:
                conn.execute(
                    """
                    UPDATE events
                    SET
                        latitude = NULL,
                        longitude = NULL,
                        distance_miles = NULL,
                        tier = NULL,
                        geo_validation_status =
                            'rejected_source_coordinates',
                        geo_validation_reason = ?,
                        reverse_geocode_name = ?
                    WHERE id = ?
                    """,
                    (
                        (
                            "Source coordinates reverse-geocode "
                            "to a state conflicting with event "
                            "metadata; coordinates cleared for "
                            "forward geocoding."
                        ),
                        display_name,
                        row["id"],
                    ),
                )

                rejected += 1

                print(
                    "  ACTION: REJECT coordinates; "
                    "send to forward geocoder."
                )

                continue

            conn.execute(
                """
                UPDATE events
                SET
                    geo_validation_status = 'review',
                    geo_validation_reason = ?,
                    reverse_geocode_name = ?
                WHERE id = ?
                """,
                (
                    (
                        "Remote source coordinate could not be "
                        "deterministically reconciled."
                    ),
                    display_name,
                    row["id"],
                ),
            )

            review += 1

            print(
                "  ACTION: REVIEW"
            )

        conn.commit()

    print()
    print("=" * 78)
    print(f"City metadata repaired:      {repaired}")
    print(f"Source coordinates rejected: {rejected}")
    print(f"Needs review:                {review}")
    print("=" * 78)


if __name__ == "__main__":
    main()
