from __future__ import annotations

from app.collectors.event_quality import sanitize_events

import argparse

from playwright.sync_api import (
    sync_playwright,
)

from app.collectors import (
    official_web_events
    as official,
)

from app.collectors.browser_fallback_events import (
    collect_source,
)

from app.collectors.regional_source_pack import (
    REGIONAL_IDS,
    REGIONAL_SOURCES,
    REGIONS,
    names_for_region,
)

from app.services.database import connect


official.REGISTRY_IDS.update(
    REGIONAL_IDS
)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run existing Playwright event "
            "collector against regional sources."
        )
    )

    parser.add_argument(
        "--region",
        choices=[
            "all",
            "huntsville",
            "mobile",
            "daytona_beach",
            "pensacola",
        ],
        default="all",
    )

    parser.add_argument(
        "--source",
        action="append",
        help=(
            "Run an exact source name. "
            "May be supplied more than once."
        ),
    )

    parser.add_argument(
        "--list",
        action="store_true",
    )

    args = parser.parse_args()

    if args.list:
        for source in REGIONAL_SOURCES:
            print(
                f"{source['region']:<15} "
                f"{source['name']}"
            )

        return

    if args.source:
        target_names = set(
            args.source
        )

    elif args.region == "all":
        target_names = {
            source["name"]
            for source
            in REGIONAL_SOURCES
        }

    else:
        target_names = (
            names_for_region(
                args.region
            )
        )

    targets = [
        source
        for source
        in official.SOURCES
        if source["name"]
        in target_names
    ]

    missing = (
        target_names
        - {
            source["name"]
            for source in targets
        }
    )

    if missing:
        print(
            "WARNING: missing from "
            "official source registry:"
        )

        for name in sorted(
            missing
        ):
            print(
                f"  {name}"
            )

    print(
        "===== REGIONAL BROWSER RUN ====="
    )

    for source in targets:
        print(
            f"{source['region']:<15} "
            f"{source['name']}"
        )

    totals = {
        "new": 0,
        "changed": 0,
        "unchanged": 0,
        "errors": 0,
    }

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=True,
        )

        context = browser.new_context(
            viewport={
                "width": 1440,
                "height": 1200,
            },
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 "
                "(X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/151.0.0.0 "
                "Safari/537.36"
            ),
        )

        page = context.new_page()

        with connect() as conn:

            for source in targets:

                events = collect_source(
                    page,
                    source,
                )

                events = sanitize_events(
                    source,
                    events,
                )

                counts = {
                    "new": 0,
                    "changed": 0,
                    "unchanged": 0,
                    "errors": 0,
                }

                for event in events:

                    try:
                        status = (
                            official.upsert_event(
                                conn,
                                source,
                                event,
                            )
                        )

                    except Exception as exc:
                        counts[
                            "errors"
                        ] += 1

                        totals[
                            "errors"
                        ] += 1

                        print(
                            "IMPORT ERROR: "
                            f"{event.get('title')} "
                            f"-> {exc}"
                        )

                        continue

                    counts[
                        status
                    ] += 1

                    totals[
                        status
                    ] += 1

                conn.commit()

                print(
                    "RESULT: "
                    f"new={counts['new']} "
                    f"changed={counts['changed']} "
                    f"unchanged={counts['unchanged']} "
                    f"errors={counts['errors']}"
                )

        context.close()
        browser.close()

    print()
    print(
        "=" * 72
    )
    print(
        " REGIONAL BROWSER RUN COMPLETE"
    )
    print(
        "=" * 72
    )

    for key, value in totals.items():
        print(
            f"{key.title():12}: "
            f"{value}"
        )


if __name__ == "__main__":
    main()
