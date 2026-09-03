from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json

import requests
from bs4 import BeautifulSoup

from app.services.database import connect
from app.services.source_registry import load_sources


ROOT = Path("/mnt/appdata/ha-services/local-events")
EXPORT_DIR = ROOT / "data/export"

TZ = ZoneInfo("America/Chicago")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/126 Safari/537.36 "
        "LocalEventsIntelligenceBoard/1.0"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def now_iso():
    return datetime.now(TZ).isoformat(timespec="seconds")


def walk_json(node):
    if isinstance(node, dict):
        yield node

        for value in node.values():
            yield from walk_json(value)

    elif isinstance(node, list):
        for value in node:
            yield from walk_json(value)


def is_event_type(value):
    if isinstance(value, str):
        return value.lower() == "event"

    if isinstance(value, list):
        return any(
            isinstance(item, str)
            and item.lower() == "event"
            for item in value
        )

    return False


def extract_jsonld_events(html):
    soup = BeautifulSoup(html, "html.parser")

    events = []

    for script in soup.find_all(
        "script",
        attrs={"type": "application/ld+json"},
    ):
        raw = script.string or script.get_text()

        if not raw or not raw.strip():
            continue

        try:
            payload = json.loads(raw)
        except Exception:
            continue

        for item in walk_json(payload):
            if is_event_type(item.get("@type")):
                events.append(item)

    return events


def event_link_count(html, base_url):
    soup = BeautifulSoup(html, "html.parser")

    links = set()

    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()

        if not href:
            continue

        lower = href.lower()

        if (
            "/event" in lower
            or "/events/" in lower
            or "calendar" in lower
        ):
            links.add(href)

    return len(links)


def source_db_update(source, status, error=None):
    timestamp = now_iso()

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO event_sources (
                name,
                enabled,
                source_type,
                tier_focus,
                last_attempt,
                last_success,
                status,
                failure_count,
                last_error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT(name)
            DO UPDATE SET
                enabled = excluded.enabled,
                source_type = excluded.source_type,
                tier_focus = excluded.tier_focus,
                last_attempt = excluded.last_attempt,
                last_success =
                    CASE
                        WHEN excluded.status = 'online'
                        THEN excluded.last_success
                        ELSE event_sources.last_success
                    END,
                status = excluded.status,
                failure_count =
                    CASE
                        WHEN excluded.status = 'online'
                        THEN 0
                        ELSE event_sources.failure_count + 1
                    END,
                last_error = excluded.last_error
            """,
            (
                source["name"],
                1 if source.get("enabled", True) else 0,
                source.get("collector"),
                source.get("region"),
                timestamp,
                timestamp if status == "online" else None,
                status,
                0 if status == "online" else 1,
                error,
            ),
        )

        conn.commit()


def probe_source(session, source):
    collector = source.get("collector")

    if collector == "ticketmaster_api":
        source_db_update(
            source,
            "configured",
            "API source; requires TICKETMASTER_API_KEY",
        )

        return {
            "id": source["id"],
            "name": source["name"],
            "status": "configured",
            "http": None,
            "jsonld_events": None,
            "event_links": None,
            "final_url": source["url"],
            "note": "API key required",
        }

    try:
        response = session.get(
            source["url"],
            timeout=(7, 30),
            allow_redirects=True,
        )

        status_code = response.status_code

        if status_code >= 400:
            status = (
                "blocked"
                if status_code in {401, 403, 429}
                else "failed"
            )

            message = f"HTTP {status_code}"

            source_db_update(
                source,
                status,
                message,
            )

            return {
                "id": source["id"],
                "name": source["name"],
                "status": status,
                "http": status_code,
                "jsonld_events": 0,
                "event_links": 0,
                "final_url": response.url,
                "note": message,
            }

        html = response.text

        jsonld = extract_jsonld_events(html)

        links = event_link_count(
            html,
            response.url,
        )

        source_db_update(
            source,
            "online",
            None,
        )

        sample_titles = []

        for event in jsonld[:5]:
            title = event.get("name")

            if title:
                sample_titles.append(str(title))

        return {
            "id": source["id"],
            "name": source["name"],
            "status": "online",
            "http": status_code,
            "jsonld_events": len(jsonld),
            "event_links": links,
            "bytes": len(response.content),
            "final_url": response.url,
            "sample_titles": sample_titles,
        }

    except Exception as exc:
        source_db_update(
            source,
            "failed",
            str(exc),
        )

        return {
            "id": source["id"],
            "name": source["name"],
            "status": "failed",
            "http": None,
            "jsonld_events": 0,
            "event_links": 0,
            "final_url": source["url"],
            "note": str(exc),
        }


def main():
    sources = load_sources()

    session = requests.Session()
    session.headers.update(HEADERS)

    results = []

    print("=" * 90)
    print(" LOCAL EVENTS — 20 SOURCE PROBE")
    print("=" * 90)

    for number, source in enumerate(
        sources,
        start=1,
    ):
        print(
            f"[{number:02}/{len(sources):02}] "
            f"{source['name']}"
        )

        result = probe_source(
            session,
            source,
        )

        results.append(result)

        print(
            f"    status={result['status']} "
            f"http={result.get('http')} "
            f"jsonld={result.get('jsonld_events')} "
            f"links={result.get('event_links')}"
        )

        samples = result.get("sample_titles") or []

        for sample in samples[:3]:
            print(f"      • {sample}")

    EXPORT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    stamp = datetime.now(TZ).strftime(
        "%Y%m%d-%H%M%S"
    )

    report_path = (
        EXPORT_DIR
        / f"source-probe-{stamp}.json"
    )

    report = {
        "generated_at": now_iso(),
        "source_count": len(sources),
        "results": results,
    }

    report_path.write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    online = sum(
        item["status"] == "online"
        for item in results
    )

    blocked = sum(
        item["status"] == "blocked"
        for item in results
    )

    failed = sum(
        item["status"] == "failed"
        for item in results
    )

    configured = sum(
        item["status"] == "configured"
        for item in results
    )

    structured = sum(
        (item.get("jsonld_events") or 0) > 0
        for item in results
    )

    print()
    print("=" * 90)
    print(" PROBE SUMMARY")
    print("=" * 90)
    print(f"Sources:             {len(results)}")
    print(f"Online:              {online}")
    print(f"API/configured:      {configured}")
    print(f"Blocked:             {blocked}")
    print(f"Failed:              {failed}")
    print(f"JSON-LD event feeds: {structured}")
    print(f"Report:              {report_path}")
    print("=" * 90)


if __name__ == "__main__":
    main()
