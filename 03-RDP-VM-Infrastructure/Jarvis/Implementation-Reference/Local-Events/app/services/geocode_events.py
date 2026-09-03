from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import time

import requests

from app.services.database import connect


ROOT = Path(
    "/mnt/appdata/ha-services/local-events"
)

CACHE_FILE = (
    ROOT
    / "cache/venues/geocode-cache.json"
)

TZ = ZoneInfo(
    "America/Chicago"
)

NOMINATIM = (
    "https://nominatim.openstreetmap.org/search"
)

# Public Nominatim limit is 1 request/sec.
# Stay slightly below that.
REQUEST_DELAY = 1.15

HEADERS = {
    "User-Agent": (
        "LocalEventsIntelligenceBoard/1.0 "
        "private-home-assistant-dashboard"
    ),
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


def raw_address(row):
    try:
        data = json.loads(
            row["raw_json"] or "{}"
        )
    except Exception:
        return None

    location = (
        data.get("location")
        or {}
    )

    if isinstance(
        location,
        list,
    ):
        location = (
            location[0]
            if location
            else {}
        )

    if not isinstance(
        location,
        dict,
    ):
        return None

    address = (
        location.get("address")
        or {}
    )

    if isinstance(
        address,
        str,
    ):
        address = address.strip()
        return address or None

    if not isinstance(
        address,
        dict,
    ):
        return None

    parts = [
        address.get(
            "streetAddress"
        ),
        address.get(
            "addressLocality"
        ),
        address.get(
            "addressRegion"
        ),
        address.get(
            "postalCode"
        ),
    ]

    parts = [
        str(part).strip()
        for part in parts
        if part
    ]

    return (
        ", ".join(parts)
        if parts
        else None
    )


def candidate_queries(row):
    venue = (
        row["venue"] or ""
    ).strip()

    city = (
        row["city"] or ""
    ).strip()

    state = (
        row["state"] or ""
    ).strip()

    address = raw_address(
        row
    )

    candidates = []

    if address:
        candidates.append(
            (
                ", ".join(
                    part
                    for part in [
                        address,
                        city,
                        state,
                        "USA",
                    ]
                    if part
                ),
                "address",
            )
        )

    if venue and city:
        candidates.append(
            (
                ", ".join(
                    part
                    for part in [
                        venue,
                        city,
                        state,
                        "USA",
                    ]
                    if part
                ),
                "venue",
            )
        )

    if city:
        candidates.append(
            (
                ", ".join(
                    part
                    for part in [
                        city,
                        state,
                        "USA",
                    ]
                    if part
                ),
                "city",
            )
        )

    # Preserve order while removing duplicates.
    unique = []
    seen = set()

    for query, precision in candidates:
        key = query.casefold()

        if key in seen:
            continue

        seen.add(key)

        unique.append(
            (
                query,
                precision,
            )
        )

    return unique


def lookup(
    session,
    query,
):
    response = session.get(
        NOMINATIM,
        params={
            "q": query,
            "format": "jsonv2",
            "limit": 1,
            "countrycodes": "us",
        },
        timeout=20,
    )

    response.raise_for_status()

    results = response.json()

    if not results:
        return None

    item = results[0]

    return {
        "latitude": float(
            item["lat"]
        ),
        "longitude": float(
            item["lon"]
        ),
        "display_name": item.get(
            "display_name"
        ),
    }


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
                venue,
                city,
                state,
                latitude,
                longitude,
                raw_json
            FROM events
            WHERE active = 1
              AND canonical = 1
            ORDER BY city, venue, title
            """
        ).fetchall()

        source_coords = 0
        updated = 0
        cache_hits = 0
        network_queries = 0
        unresolved = 0

        print(
            "=" * 78
        )
        print(
            " LOCAL EVENTS — GEOCODING"
        )
        print(
            "=" * 78
        )

        for row in rows:

            if (
                row["latitude"] is not None
                and row["longitude"] is not None
            ):
                source_coords += 1

                # Preserve coordinates supplied
                # directly by event source.
                if not row["id"]:
                    pass

                continue

            found = None
            used_query = None
            used_precision = None

            for (
                query,
                precision,
            ) in candidate_queries(row):

                key = query.casefold()

                if key in cache:

                    cached = cache[
                        key
                    ]

                    cache_hits += 1

                    if cached:
                        found = cached
                        used_query = query
                        used_precision = precision
                        break

                    continue

                print(
                    f"LOOKUP #{row['id']:03}: "
                    f"{query}"
                )

                try:
                    result = lookup(
                        session,
                        query,
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

                network_queries += 1

                time.sleep(
                    REQUEST_DELAY
                )

                if result:
                    found = result
                    used_query = query
                    used_precision = precision
                    break

            if not found:
                unresolved += 1

                print(
                    f"  UNRESOLVED: "
                    f"{row['title']}"
                )

                continue

            conn.execute(
                """
                UPDATE events
                SET
                    latitude = ?,
                    longitude = ?,
                    geocode_query = ?,
                    geocode_provider = 'nominatim',
                    geocode_precision = ?,
                    geocoded_at = ?
                WHERE id = ?
                """,
                (
                    found[
                        "latitude"
                    ],
                    found[
                        "longitude"
                    ],
                    used_query,
                    used_precision,
                    now_iso(),
                    row["id"],
                ),
            )

            updated += 1

        conn.commit()

    print()
    print(
        "=" * 78
    )
    print(
        f"Source coordinates: {source_coords}"
    )
    print(
        f"Newly geocoded:     {updated}"
    )
    print(
        f"Cache hits:         {cache_hits}"
    )
    print(
        f"Network queries:    {network_queries}"
    )
    print(
        f"Unresolved:         {unresolved}"
    )
    print(
        f"Cache:              {CACHE_FILE}"
    )
    print(
        "=" * 78
    )


if __name__ == "__main__":
    main()
