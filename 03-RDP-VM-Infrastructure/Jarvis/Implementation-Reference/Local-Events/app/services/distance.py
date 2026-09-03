from math import (
    asin,
    cos,
    radians,
    sin,
    sqrt,
)
from pathlib import Path

import yaml

from app.services.database import connect
from app.services.ha_client import (
    get_home_location,
)


ROOT = Path(
    "/mnt/appdata/ha-services/local-events"
)

CONFIG_FILE = (
    ROOT
    / "config/local-events.yaml"
)

EARTH_RADIUS_MILES = 3958.7613


def haversine(
    lat1,
    lon1,
    lat2,
    lon2,
):
    lat1 = radians(
        float(lat1)
    )

    lon1 = radians(
        float(lon1)
    )

    lat2 = radians(
        float(lat2)
    )

    lon2 = radians(
        float(lon2)
    )

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        sin(
            dlat / 2
        ) ** 2
        +
        cos(lat1)
        * cos(lat2)
        * sin(
            dlon / 2
        ) ** 2
    )

    return (
        2
        * EARTH_RADIUS_MILES
        * asin(
            sqrt(a)
        )
    )


def classify_tier(
    miles,
    t1_max,
    t2_max,
):
    if miles <= t1_max:
        return "T1"

    if miles <= t2_max:
        return "T2"

    return "T3"


def main():
    config = yaml.safe_load(
        CONFIG_FILE.read_text(
            encoding="utf-8"
        )
    )

    home = get_home_location()

    home_lat = home[
        "latitude"
    ]

    home_lon = home[
        "longitude"
    ]

    t1_max = float(
        config["distance"][
            "tier_1_max_miles"
        ]
    )

    t2_max = float(
        config["distance"][
            "tier_2_max_miles"
        ]
    )

    counts = {
        "T1": 0,
        "T2": 0,
        "T3": 0,
    }

    unresolved = 0

    with connect() as conn:

        rows = conn.execute(
            """
            SELECT
                id,
                latitude,
                longitude
            FROM events
            WHERE active = 1
              AND canonical = 1
            """
        ).fetchall()

        for row in rows:

            if (
                row["latitude"] is None
                or row["longitude"] is None
            ):
                unresolved += 1
                continue

            miles = haversine(
                home_lat,
                home_lon,
                row["latitude"],
                row["longitude"],
            )

            tier = classify_tier(
                miles,
                t1_max,
                t2_max,
            )

            conn.execute(
                """
                UPDATE events
                SET
                    distance_miles = ?,
                    tier = ?
                WHERE id = ?
                """,
                (
                    round(
                        miles,
                        1,
                    ),
                    tier,
                    row["id"],
                ),
            )

            counts[
                tier
            ] += 1

        conn.commit()

    print(
        "=" * 76
    )
    print(
        " LOCAL EVENTS — DISTANCE TIERS"
    )
    print(
        "=" * 76
    )

    print(
        "HA connection: PASS"
    )

    print(
        "Home coordinates: "
        "loaded privately from HA"
    )

    print()

    print(
        f"T1  <= {t1_max:g} mi : "
        f"{counts['T1']}"
    )

    print(
        f"T2  >{t1_max:g}-"
        f"{t2_max:g} mi : "
        f"{counts['T2']}"
    )

    print(
        f"T3  > {t2_max:g} mi : "
        f"{counts['T3']}"
    )

    print(
        f"Unresolved:       "
        f"{unresolved}"
    )

    print(
        "=" * 76
    )


if __name__ == "__main__":
    main()
