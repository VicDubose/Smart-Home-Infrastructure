from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import json
import os

import requests

from app.services.database import connect


TZ = ZoneInfo("America/Chicago")

ENV_FILE = (
    "/srv/docker/stacks/al-power/.env"
)


def load_env():
    result = {}

    with open(
        ENV_FILE,
        "r",
        encoding="utf-8",
    ) as handle:
        for line in handle:
            line = line.strip()

            if (
                not line
                or line.startswith("#")
                or "=" not in line
            ):
                continue

            key, value = (
                line.split("=", 1)
            )

            result[
                key.strip()
            ] = value.strip()

    return result


ENV = load_env()

HA_URL = ENV[
    "HA_URL"
].rstrip("/")

HA_TOKEN = ENV[
    "HA_TOKEN"
]


def publish(
    entity_id,
    state,
    attributes,
):
    response = requests.post(
        (
            f"{HA_URL}/api/states/"
            f"{entity_id}"
        ),
        headers={
            "Authorization":
                f"Bearer {HA_TOKEN}",

            "Content-Type":
                "application/json",
        },
        json={
            "state": str(state),
            "attributes": attributes,
        },
        timeout=15,
    )

    response.raise_for_status()


def main():
    with connect() as conn:

        stats = conn.execute(
            """
            SELECT
                COUNT(*) AS total,

                SUM(
                    tier = 'T1'
                ) AS t1,

                SUM(
                    tier = 'T2'
                ) AS t2,

                SUM(
                    tier = 'T3'
                ) AS t3,

                SUM(
                    seasonal_event = 1
                ) AS seasonal,

                SUM(
                    season_boost_active = 1
                ) AS boosted,

                SUM(
                    ai_processed = 1
                ) AS ai_done

            FROM events

            WHERE canonical = 1
              AND active = 1
            """
        ).fetchone()

        top = conn.execute(
            """
            SELECT
                clean_title,
                title,
                score,
                tier,
                priority_tier,
                distance_miles,
                primary_category

            FROM events

            WHERE canonical = 1
              AND active = 1
              AND score IS NOT NULL

            ORDER BY
                score DESC,
                distance_miles ASC

            LIMIT 1
            """
        ).fetchone()

        queue = conn.execute(
            """
            SELECT COUNT(*) AS jobs
            FROM ai_jobs
            WHERE status IN (
                'pending',
                'running'
            )
            """
        ).fetchone()[
            "jobs"
        ]

        duplicates = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM events
            WHERE canonical = 0
            """
        ).fetchone()[
            "count"
        ]

        sources = conn.execute(
            """
            SELECT COUNT(
                DISTINCT source_name
            ) AS count
            FROM events
            WHERE canonical = 1
              AND active = 1
            """
        ).fetchone()[
            "count"
        ]

    now = datetime.now(
        TZ
    ).isoformat(
        timespec="seconds"
    )

    common = {
        "icon":
            "mdi:calendar-star",

        "last_update":
            now,

        "dashboard_url":
            "http://192.168.50.51:8787",
    }

    entities = {
        "sensor.local_events_total": (
            stats["total"],
            {
                **common,
                "friendly_name":
                    "Local Events Total",
            },
        ),

        "sensor.local_events_50mi": (
            stats["t1"] or 0,
            {
                **common,
                "friendly_name":
                    "Local Events Within 50 Miles",
            },
        ),

        "sensor.local_events_100mi": (
            stats["t2"] or 0,
            {
                **common,
                "friendly_name":
                    "Local Events 50-100 Miles",
            },
        ),

        "sensor.local_events_travel": (
            stats["t3"] or 0,
            {
                **common,
                "friendly_name":
                    "Local Events Travel Watchlist",
            },
        ),

        "sensor.local_events_seasonal": (
            stats["seasonal"] or 0,
            {
                **common,
                "friendly_name":
                    "Seasonal Events",
                "boosted":
                    stats["boosted"] or 0,
            },
        ),

        "sensor.event_ai_queue": (
            queue,
            {
                **common,
                "friendly_name":
                    "Event AI Queue",
            },
        ),

        "sensor.event_ai_processed": (
            stats["ai_done"] or 0,
            {
                **common,
                "friendly_name":
                    "Events AI Processed",
            },
        ),

        "sensor.event_duplicates_removed": (
            duplicates,
            {
                **common,
                "friendly_name":
                    "Event Duplicates Removed",
            },
        ),

        "sensor.event_sources_online": (
            sources,
            {
                **common,
                "friendly_name":
                    "Event Sources With Active Data",
            },
        ),
    }

    if top:
        title = (
            top["clean_title"]
            or top["title"]
        )

        entities[
            "sensor.local_events_top_pick"
        ] = (
            title,
            {
                **common,

                "friendly_name":
                    "Local Events Top Pick",

                "score":
                    top["score"],

                "category":
                    top[
                        "primary_category"
                    ],

                "tier":
                    top["tier"],

                "priority_tier":
                    top[
                        "priority_tier"
                    ],

                "distance_miles":
                    top[
                        "distance_miles"
                    ],
            },
        )

    healthy = (
        stats["total"] > 0
        and queue == 0
    )

    entities[
        "binary_sensor.event_system_healthy"
    ] = (
        "on"
        if healthy
        else "off",
        {
            **common,

            "friendly_name":
                "Local Events System Healthy",

            "active_events":
                stats["total"],

            "ai_queue":
                queue,
        },
    )

    for (
        entity_id,
        (
            state,
            attributes,
        ),
    ) in entities.items():

        publish(
            entity_id,
            state,
            attributes,
        )

        print(
            f"PASS: {entity_id}"
        )


if __name__ == "__main__":
    main()
