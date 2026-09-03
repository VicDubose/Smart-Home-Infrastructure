from __future__ import annotations

from datetime import datetime
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo
import re

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from app.collectors.official_web_events import (
    SOURCES,
    clean_text,
    parse_dt,
    in_window,
    parse_jsonld,
    normalize_jsonld,
    fallback_event,
    upsert_event,
)
from app.services.database import connect


TZ = ZoneInfo("America/Chicago")
CURRENT_YEAR = datetime.now(TZ).year

TARGET_NAMES = {
    "Ober Mountain",
    "Visit Music City",
    "Visit Mobile",
    "Visit Orlando",
}

DETAIL_LIMIT = 70

MONTH_DATE_RE = re.compile(
    r"\b("
    r"January|February|March|April|May|June|July|"
    r"August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
    r")\s+\d{1,2}"
    r"(?:,\s*\d{4})?",
    re.I,
)

NUMERIC_DATE_RE = re.compile(
    r"\b\d{1,2}/\d{1,2}/(?:\d{2}|\d{4})\b"
)

GENERIC_TITLES = {
    "details",
    "learn more",
    "read more",
    "view event",
    "view events",
    "events",
    "calendar",
    "more info",
    "visit website",
}


def render(page, url):
    response = page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=60000,
    )

    page.wait_for_timeout(2500)

    # Trigger lazy-loaded cards.
    previous_height = 0

    for _ in range(8):
        height = page.evaluate(
            "document.body.scrollHeight"
        )

        page.evaluate(
            "window.scrollTo(0, document.body.scrollHeight)"
        )

        page.wait_for_timeout(600)

        if height == previous_height:
            break

        previous_height = height

    return (
        page.content(),
        response.status if response else None,
    )


def parse_card_date(text):
    matches = []

    matches.extend(
        match.group(0)
        for match in MONTH_DATE_RE.finditer(text)
    )

    matches.extend(
        match.group(0)
        for match in NUMERIC_DATE_RE.finditer(text)
    )

    for candidate in matches:
        value = candidate

        if not re.search(
            r"\b20\d{2}\b",
            value,
        ):
            value = (
                f"{value}, {CURRENT_YEAR}"
            )

        dt = parse_dt(value)

        if dt and in_window(dt):
            return dt

    return None


def valid_title(title):
    if not title:
        return False

    lowered = title.casefold().strip()

    if lowered in GENERIC_TITLES:
        return False

    if len(title) < 4:
        return False

    if len(title) > 180:
        return False

    return True


def event_links(soup, base_url):
    base_host = urlparse(
        base_url
    ).netloc

    results = []
    seen = set()

    for anchor in soup.find_all(
        "a",
        href=True,
    ):
        href = urljoin(
            base_url,
            anchor["href"],
        )

        parsed = urlparse(href)

        if parsed.netloc != base_host:
            continue

        path = parsed.path.lower()

        eventish = (
            "/event/" in path
            or "/events/" in path
            or "/nashville-events/" in path
        )

        if not eventish:
            continue

        if (
            href.rstrip("/")
            == base_url.rstrip("/")
        ):
            continue

        if href in seen:
            continue

        seen.add(href)
        results.append(href)

    return results[:DETAIL_LIMIT]


def listing_card_events(
    soup,
    source,
):
    results = []
    seen = set()

    base_host = urlparse(
        source["url"]
    ).netloc

    for anchor in soup.find_all(
        "a",
        href=True,
    ):
        href = urljoin(
            source["url"],
            anchor["href"],
        )

        if (
            urlparse(href).netloc
            != base_host
        ):
            continue

        title = clean_text(
            anchor.get_text(
                " ",
                strip=True,
            )
        )

        if not valid_title(title):
            continue

        node = anchor

        # Look at the surrounding event card.
        for _ in range(4):
            if node.parent is not None:
                node = node.parent

        card_text = clean_text(
            node.get_text(
                " ",
                strip=True,
            )
        )

        start = parse_card_date(
            card_text
        )

        if not start:
            continue

        key = (
            title.casefold(),
            start.isoformat(),
            href,
        )

        if key in seen:
            continue

        seen.add(key)

        results.append(
            {
                "title":
                    title,

                "description":
                    card_text[:1200],

                "start_time":
                    start.isoformat(),

                "end_time":
                    None,

                "venue":
                    None,

                "city":
                    source["city"],

                "state":
                    source["state"],

                "latitude":
                    None,

                "longitude":
                    None,

                "url":
                    href,

                "raw": {
                    "browser_listing":
                        True,
                    "card_text":
                        card_text,
                },
            }
        )

    return results



def collect_iframe_events(
    page,
    source,
):
    """
    Collect events from embedded calendars such as
    Time.ly iframes without creating a second scraper.
    """

    results = []

    frames = [
        frame
        for frame in page.frames
        if frame != page.main_frame
        and frame.url
        and frame.url != "about:blank"
    ]

    if not frames:
        return results

    print(
        f"Embedded frames discovered: "
        f"{len(frames)}"
    )

    for frame in frames:

        try:
            html = frame.content()

        except Exception as exc:
            print(
                "  FRAME SKIP: "
                f"{type(exc).__name__}"
            )
            continue

        if not html:
            continue

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        frame_source = dict(
            source
        )

        frame_source[
            "url"
        ] = frame.url

        before = len(
            results
        )

        # Structured events inside frame.
        for obj in parse_jsonld(
            soup
        ):
            event = normalize_jsonld(
                obj,
                source,
                frame.url,
            )

            if event:
                results.append(
                    event
                )

        # Rendered event cards inside frame.
        results.extend(
            listing_card_events(
                soup,
                frame_source,
            )
        )

        added = (
            len(results)
            - before
        )

        print(
            "  FRAME: "
            f"{frame.url[:80]} "
            f"events={added}"
        )

    return results


def collect_source(
    page,
    source,
):
    print()
    print("=" * 72)
    print(
        f" {source['name']}"
    )
    print("=" * 72)

    try:
        html, status = render(
            page,
            source["url"],
        )

    except Exception as exc:
        print(
            f"BROWSER FETCH FAILED: {exc}"
        )
        return []

    print(
        f"Browser HTTP status: {status}"
    )

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    events = []

    # 1. JSON-LD after JavaScript rendering.
    for obj in parse_jsonld(soup):
        event = normalize_jsonld(
            obj,
            source,
            source["url"],
        )

        if event:
            events.append(event)

    # 2. Visible event cards on the rendered listing.
    card_events = listing_card_events(
        soup,
        source,
    )

    events.extend(card_events)

    print(
        f"Rendered listing events: "
        f"{len(card_events)}"
    )

    iframe_events = (
        collect_iframe_events(
            page,
            source,
        )
    )

    events.extend(
        iframe_events
    )

    if iframe_events:
        print(
            "Embedded calendar events: "
            f"{len(iframe_events)}"
        )

    # 3. Follow rendered event links.
    links = event_links(
        soup,
        source["url"],
    )

    print(
        f"Rendered detail links: "
        f"{len(links)}"
    )

    for number, link in enumerate(
        links,
        1,
    ):
        try:
            detail_html, detail_status = (
                render(
                    page,
                    link,
                )
            )

        except Exception:
            continue

        if (
            detail_status is not None
            and detail_status >= 400
        ):
            continue

        detail = BeautifulSoup(
            detail_html,
            "html.parser",
        )

        found = False

        for obj in parse_jsonld(
            detail
        ):
            event = normalize_jsonld(
                obj,
                source,
                link,
            )

            if event:
                events.append(event)
                found = True

        if not found:
            event = fallback_event(
                detail,
                source,
                link,
            )

            if event:
                events.append(event)

    # Final exact-event dedupe.
    unique = {}

    for event in events:
        key = (
            event["title"].casefold(),
            event["start_time"],
            event.get("url"),
        )

        unique[key] = event

    final = list(
        unique.values()
    )

    print(
        f"30-day browser events: "
        f"{len(final)}"
    )

    return final


def main():
    targets = [
        source
        for source in SOURCES
        if source["name"]
        in TARGET_NAMES
    ]

    print(
        "===== BROWSER FALLBACK SOURCES ====="
    )

    for source in targets:
        print(
            f"  {source['name']}"
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

                counts = {
                    "new": 0,
                    "changed": 0,
                    "unchanged": 0,
                    "errors": 0,
                }

                for event in events:
                    try:
                        status = upsert_event(
                            conn,
                            source,
                            event,
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
                    "New / changed / "
                    "unchanged / errors: "
                    f"{counts['new']} / "
                    f"{counts['changed']} / "
                    f"{counts['unchanged']} / "
                    f"{counts['errors']}"
                )

        context.close()
        browser.close()

    print()
    print("=" * 72)
    print(
        " BROWSER FALLBACK COMPLETE"
    )
    print("=" * 72)

    for name, value in totals.items():
        print(
            f"{name.title():12}: {value}"
        )


if __name__ == "__main__":
    main()
