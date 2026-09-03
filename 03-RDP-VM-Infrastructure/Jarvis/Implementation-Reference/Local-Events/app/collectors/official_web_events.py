from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag
from zoneinfo import ZoneInfo
import json
import re
import time

import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

from app.services.database import connect
from app.services.normalize import event_key as build_event_key


TZ = ZoneInfo("America/Chicago")
TODAY = datetime.now(TZ)
WINDOW_END = TODAY + timedelta(days=30)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 LocalEventsIntelligenceBoard/1.6 "
        "(private Home Assistant event dashboard)"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

TIMEOUT = 25
DETAIL_LIMIT = 45
REQUEST_DELAY = 0.20


def load_registry_ids():
    import yaml

    config_path = (
        Path(
            "/mnt/appdata/ha-services/local-events"
        )
        / "config/sources.yaml"
    )

    data = yaml.safe_load(
        config_path.read_text(
            encoding="utf-8"
        )
    )

    if isinstance(data, dict):
        rows = data.get(
            "sources",
            []
        )

    elif isinstance(data, list):
        rows = data

    else:
        raise RuntimeError(
            "Unexpected sources.yaml format"
        )

    result = {}

    for row in rows:
        name = str(
            row.get("name", "")
        ).strip()

        source_id = str(
            row.get("id", "")
        ).strip()

        if name and source_id:
            result[name] = source_id

    return result


REGISTRY_IDS = load_registry_ids()


SOURCES = [
    {
        "name": "Visit Tuscaloosa",
        "url": "https://visittuscaloosa.com/events/",
        "city": "Tuscaloosa",
        "state": "AL",
    },
    {
        "name": "Oak Mountain State Park",
        "url": (
            "https://www.alapark.com/parks/"
            "oak-mountain-state-park/"
            "park-events-and-programs"
        ),
        "city": "Pelham",
        "state": "AL",
    },
    {
        "name": "Gatlinburg CVB",
        "url": "https://www.gatlinburg.com/events/all-events/",
        "city": "Gatlinburg",
        "state": "TN",
    },
    {
        "name": "Ober Mountain",
        "url": "https://www.obermountain.com/events",
        "city": "Gatlinburg",
        "state": "TN",
    },
    {
        "name": "Visit Music City",
        "url": (
            "https://www.visitmusiccity.com/"
            "nashville-events/upcoming-events"
        ),
        "city": "Nashville",
        "state": "TN",
    },
    {
        "name": "Visit Mobile",
        "url": "https://www.mobile.org/events/",
        "city": "Mobile",
        "state": "AL",
    },
    {
        "name": "Daytona Beach Area CVB",
        "url": (
            "https://www.daytonabeach.com/"
            "events/all-events/"
        ),
        "city": "Daytona Beach",
        "state": "FL",
    },
    {
        "name": "Visit Orlando",
        "url": "https://www.visitorlando.com/events/",
        "city": "Orlando",
        "state": "FL",
    },
]


MONTH_RE = re.compile(
    r"\b("
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|"
    r"May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
    r")\s+\d{1,2}"
    r"(?:,\s*\d{4})?"
    r"(?:\s*(?:at|•)?\s*"
    r"\d{1,2}:\d{2}\s*(?:AM|PM)?)?",
    re.I,
)

NUMERIC_DATE_RE = re.compile(
    r"\b\d{1,2}/\d{1,2}/\d{4}"
    r"(?:\s+at\s+\d{1,2}:\d{2}\s*(?:AM|PM))?",
    re.I,
)


def now_iso():
    return datetime.now(TZ).isoformat(timespec="seconds")


def clean_text(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or ""),
    ).strip()


def walk_json(value):
    if isinstance(value, dict):
        yield value

        for child in value.values():
            yield from walk_json(child)

    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def is_event_object(obj):
    kind = obj.get("@type")

    if isinstance(kind, list):
        return "Event" in kind

    return kind == "Event"


def parse_jsonld(soup):
    found = []

    for script in soup.select(
        'script[type="application/ld+json"]'
    ):
        try:
            raw = script.string or script.get_text()

            data = json.loads(raw)

        except Exception:
            continue

        for obj in walk_json(data):
            if is_event_object(obj):
                found.append(obj)

    return found


def address_parts(location):
    venue = None
    city = None
    state = None
    latitude = None
    longitude = None

    if not isinstance(location, dict):
        return (
            venue,
            city,
            state,
            latitude,
            longitude,
        )

    venue = clean_text(
        location.get("name")
    ) or None

    address = location.get("address")

    if isinstance(address, dict):
        city = clean_text(
            address.get("addressLocality")
        ) or None

        state = clean_text(
            address.get("addressRegion")
        ) or None

    geo = location.get("geo")

    if isinstance(geo, dict):
        try:
            latitude = float(
                geo.get("latitude")
            )
            longitude = float(
                geo.get("longitude")
            )
        except Exception:
            latitude = None
            longitude = None

    return (
        venue,
        city,
        state,
        latitude,
        longitude,
    )


def parse_dt(value):
    if not value:
        return None

    try:
        dt = dateparser.parse(
            str(value),
            fuzzy=True,
            default=TODAY.replace(
                hour=12,
                minute=0,
                second=0,
                microsecond=0,
            ),
        )
    except Exception:
        return None

    if not dt:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=TZ
        )

    return dt


def in_window(start, end=None):
    if not start:
        return False

    end = end or start

    return (
        end >= TODAY - timedelta(days=1)
        and start <= WINDOW_END
    )


def normalize_jsonld(
    obj,
    source,
    page_url,
):
    start = parse_dt(
        obj.get("startDate")
    )

    end = parse_dt(
        obj.get("endDate")
    )

    if not in_window(
        start,
        end,
    ):
        return None

    (
        venue,
        city,
        state,
        latitude,
        longitude,
    ) = address_parts(
        obj.get("location")
    )

    title = clean_text(
        obj.get("name")
    )

    if not title:
        return None

    url = clean_text(
        obj.get("url")
    ) or page_url

    return {
        "title": title,
        "description": clean_text(
            obj.get("description")
        ),
        "start_time": start.isoformat(),
        "end_time": (
            end.isoformat()
            if end
            else None
        ),
        "venue": venue,
        "city": (
            city
            or source["city"]
        ),
        "state": (
            state
            or source["state"]
        ),
        "latitude": latitude,
        "longitude": longitude,
        "url": url,
        "raw": obj,
    }


def fallback_event(
    soup,
    source,
    page_url,
):
    title_node = soup.find("h1")

    if not title_node:
        return None

    title = clean_text(
        title_node.get_text(" ")
    )

    if (
        not title
        or len(title) > 220
    ):
        return None

    start = None

    time_node = soup.find(
        "time",
        attrs={"datetime": True},
    )

    if time_node:
        start = parse_dt(
            time_node.get("datetime")
        )

    if not start:
        text = clean_text(
            soup.get_text(" ")
        )

        match = (
            NUMERIC_DATE_RE.search(text)
            or MONTH_RE.search(text)
        )

        if match:
            candidate = match.group(0)

            if not re.search(
                r"\b20\d{2}\b",
                candidate,
            ):
                candidate += (
                    f", {TODAY.year}"
                )

            start = parse_dt(
                candidate
            )

    if not in_window(start):
        return None

    description = ""

    meta = soup.find(
        "meta",
        attrs={"name": "description"},
    )

    if meta:
        description = clean_text(
            meta.get("content")
        )

    return {
        "title": title,
        "description": description,
        "start_time": start.isoformat(),
        "end_time": None,
        "venue": None,
        "city": source["city"],
        "state": source["state"],
        "latitude": None,
        "longitude": None,
        "url": page_url,
        "raw": {
            "fallback": True,
            "title": title,
            "url": page_url,
        },
    }


def fetch(session, url):
    response = session.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT,
    )

    response.raise_for_status()

    return response.text


def candidate_links(
    soup,
    base_url,
):
    base = urlparse(base_url)

    links = []

    seen = set()

    for anchor in soup.find_all(
        "a",
        href=True,
    ):
        href = urljoin(
            base_url,
            anchor["href"],
        )

        href, _ = urldefrag(
            href
        )

        parsed = urlparse(href)

        if (
            parsed.netloc
            != base.netloc
        ):
            continue

        path = parsed.path.lower()

        if (
            "event" not in path
            and "events" not in path
        ):
            continue

        if href.rstrip("/") == (
            base_url.rstrip("/")
        ):
            continue

        bad = (
            "submit",
            "calendar?",
            "/annual-events",
            "/seasonal-events",
            "/featured-events",
        )

        if any(
            token in href.lower()
            for token in bad
        ):
            continue

        text = clean_text(
            anchor.get_text(" ")
        )

        if len(text) < 3:
            continue

        if href in seen:
            continue

        seen.add(href)
        links.append(href)

    return links[
        :DETAIL_LIMIT
    ]


def source_event_id(
    source_name,
    event,
):
    key = (
        source_name
        + "|"
        + (
            event.get("url")
            or ""
        )
        + "|"
        + event["title"]
        + "|"
        + event["start_time"]
    )

    return sha256(
        key.encode()
    ).hexdigest()[:32]


def content_hash(event):
    material = {
        key: event.get(key)
        for key in (
            "title",
            "description",
            "start_time",
            "end_time",
            "venue",
            "city",
            "state",
            "latitude",
            "longitude",
            "url",
        )
    }

    return sha256(
        json.dumps(
            material,
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def source_db_id(
    conn,
    source_name,
):
    cols = {
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(event_sources)"
        )
    }

    if "id" not in cols:
        return None

    for field in (
        "name",
        "source_name",
    ):
        if field not in cols:
            continue

        row = conn.execute(
            f"""
            SELECT id
            FROM event_sources
            WHERE {field} = ?
            LIMIT 1
            """,
            (
                source_name,
            ),
        ).fetchone()

        if row:
            return row["id"]

    return None


def queue_ai(
    conn,
    event_id,
):
    exists = conn.execute(
        """
        SELECT 1
        FROM ai_jobs
        WHERE event_id = ?
          AND job_type = 'classify_event'
          AND status IN (
              'pending',
              'running'
          )
        LIMIT 1
        """,
        (
            event_id,
        ),
    ).fetchone()

    if exists:
        return False

    conn.execute(
        """
        INSERT INTO ai_jobs (
            event_id,
            job_type,
            status,
            created_at,
            retries
        )
        VALUES (
            ?,
            'classify_event',
            'pending',
            ?,
            0
        )
        """,
        (
            event_id,
            now_iso(),
        ),
    )

    return True


def upsert_event(
    conn,
    source,
    event,
):
    cols_info = list(
        conn.execute(
            "PRAGMA table_info(events)"
        )
    )

    cols = {
        row["name"]
        for row in cols_info
    }

    source_id = REGISTRY_IDS.get(
        source["name"]
    )

    if not source_id:
        raise RuntimeError(
            "No canonical source ID for "
            f"{source['name']!r}"
        )

    eid = source_event_id(
        source["name"],
        event,
    )

    stable_event_key = build_event_key(
        source_id,
        eid,
        event["title"],
        event["start_time"],
        event.get("venue"),
    )

    digest = content_hash(
        event
    )

    timestamp = now_iso()

    existing = conn.execute(
        """
        SELECT
            id,
            content_hash
        FROM events
        WHERE event_key = ?
        LIMIT 1
        """,
        (
            stable_event_key,
        ),
    ).fetchone()

    values = {
        "event_key":
            stable_event_key,

        "source_event_id":
            eid,

        "source_name":
            source["name"],

        "title":
            event["title"],

        "description":
            event.get(
                "description"
            ),

        "start_time":
            event["start_time"],

        "end_time":
            event.get(
                "end_time"
            ),

        "venue":
            event.get(
                "venue"
            ),

        "city":
            event.get("city")
            or source["city"],

        "state":
            event.get("state")
            or source["state"],

        "latitude":
            event.get(
                "latitude"
            ),

        "longitude":
            event.get(
                "longitude"
            ),

        "active":
            1,

        "content_hash":
            digest,

        "raw_json":
            json.dumps(
                event.get(
                    "raw",
                    {},
                ),
                ensure_ascii=False,
                sort_keys=True,
            ),
    }

    if "source_url" in cols:
        values[
            "source_url"
        ] = event.get(
            "url"
        )

    if "url" in cols:
        values[
            "url"
        ] = event.get(
            "url"
        )

    if "event_url" in cols:
        values[
            "event_url"
        ] = event.get(
            "url"
        )

    sid = source_db_id(
        conn,
        source["name"],
    )

    if (
        sid is not None
        and "source_id" in cols
    ):
        values[
            "source_id"
        ] = sid

    if "last_seen" in cols:
        values[
            "last_seen"
        ] = timestamp

    if "updated_at" in cols:
        values[
            "updated_at"
        ] = timestamp

    if existing is not None:

        changed = (
            existing[
                "content_hash"
            ]
            != digest
        )

        assignments = []
        params = []

        for name, value in values.items():

            if name not in cols:
                continue

            assignments.append(
                f"{name} = ?"
            )

            params.append(
                value
            )

        if (
            changed
            and "last_changed"
            in cols
        ):
            assignments.append(
                "last_changed = ?"
            )

            params.append(
                timestamp
            )

        if changed:

            resets = {
                "ai_processed": 0,
                "ai_version": None,
                "ai_updated_at": None,

                "score": None,
                "score_breakdown": None,
                "scoring_version": None,

                "season_boost_active": 0,
                "priority_tier": None,
                "priority_reason": None,
            }

            for (
                name,
                value,
            ) in resets.items():

                if name not in cols:
                    continue

                assignments.append(
                    f"{name} = ?"
                )

                params.append(
                    value
                )

        params.append(
            existing["id"]
        )

        conn.execute(
            """
            UPDATE events
            SET
            """
            + ", ".join(
                assignments
            )
            + """
            WHERE id = ?
            """,
            params,
        )

        if changed:
            queue_ai(
                conn,
                existing["id"],
            )

            return "changed"

        return "unchanged"

    # New record.
    if "canonical" in cols:
        values[
            "canonical"
        ] = 1

    if "ai_processed" in cols:
        values[
            "ai_processed"
        ] = 0

    if "first_seen" in cols:
        values[
            "first_seen"
        ] = timestamp

    if "last_seen" in cols:
        values[
            "last_seen"
        ] = timestamp

    if "last_changed" in cols:
        values[
            "last_changed"
        ] = timestamp

    if "created_at" in cols:
        values[
            "created_at"
        ] = timestamp

    # Fill only genuinely required columns
    # that have no database default.
    for info in cols_info:

        name = info["name"]

        if (
            name == "id"
            or name in values
            or not info["notnull"]
            or info["dflt_value"]
                is not None
        ):
            continue

        column_type = (
            info["type"]
            or ""
        ).upper()

        if any(
            token in column_type
            for token in (
                "INT",
                "REAL",
                "NUM",
            )
        ):
            values[
                name
            ] = 0

        else:
            values[
                name
            ] = ""

    names = [
        name
        for name in values
        if name in cols
    ]

    placeholders = ",".join(
        "?"
        for _ in names
    )

    cursor = conn.execute(
        f"""
        INSERT INTO events (
            {",".join(names)}
        )
        VALUES (
            {placeholders}
        )
        """,
        [
            values[name]
            for name in names
        ],
    )

    queue_ai(
        conn,
        cursor.lastrowid,
    )

    return "new"



# BEGIN KRISPY KREME PROMOTION PARSER
def parse_krispy_promotions(
    soup,
    source,
):
    """
    Convert explicitly dated Krispy Kreme
    limited-time promotions into event records.

    This intentionally does not invent dates.
    Promotions without a trustworthy date
    window are ignored until a date can be
    extracted from the official page.
    """

    page_text = " ".join(
        soup.stripped_strings
    )

    if not page_text:
        return []

    range_re = re.compile(
        r"(?P<start>"
        r"\d{1,2}/\d{1,2}/"
        r"(?:20)?\d{2}"
        r")"
        r"\s*"
        r"(?:through|thru|to|[-–—])"
        r"\s*"
        r"(?P<end>"
        r"\d{1,2}/\d{1,2}/"
        r"(?:20)?\d{2}"
        r")",
        re.IGNORECASE,
    )

    stop_words = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "for",
        "with",
        "of",
        "our",
        "your",
        "this",
        "that",
        "get",
        "new",
        "now",
        "available",
        "limited",
        "time",
        "season",
        "seasonal",
        "specialty",
        "doughnut",
        "doughnuts",
        "dozen",
        "dozens",
        "collection",
        "collections",
        "krispy",
        "kreme",
    }

    def tokens(value):
        words = re.findall(
            r"[^\W_]+",
            str(value).casefold(),
            flags=re.UNICODE,
        )

        return {
            word
            for word in words
            if len(word) >= 3
            and word not in stop_words
        }

    def parse_date(value):
        dt = dateparser.parse(
            value
        )

        if dt is None:
            return None

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=TZ
            )
        else:
            dt = dt.astimezone(
                TZ
            )

        return dt.replace(
            hour=12,
            minute=0,
            second=0,
            microsecond=0,
        )

    # Find every explicit date range on the
    # official page and preserve surrounding
    # text so it can be matched to a heading.
    ranges = []

    for match in range_re.finditer(
        page_text
    ):
        start = parse_date(
            match.group("start")
        )

        end = parse_date(
            match.group("end")
        )

        if (
            start is None
            or end is None
        ):
            continue

        # Ignore promotions that have already
        # completely expired.
        if end < TODAY:
            continue

        # Ignore something too far beyond the
        # dashboard's rolling discovery window.
        if start > WINDOW_END:
            continue

        # Associate a date only with the
        # sentence that actually contains it.
        #
        # The previous implementation used
        # +/- 700 characters. That allowed the
        # Pokémon availability window to bleed
        # into unrelated offer cards such as
        # autumn lattes and fundraising deals.
        #
        # Conservative behavior is intentional:
        # if the promotion cannot be associated
        # confidently, skip it instead of
        # inventing a date.

        sentence_start = 0

        for punctuation in ".!?":
            position = page_text.rfind(
                punctuation,
                0,
                match.start(),
            )

            if position >= sentence_start:
                sentence_start = (
                    position + 1
                )

        sentence_end = len(
            page_text
        )

        endings = []

        for punctuation in ".!?":
            position = page_text.find(
                punctuation,
                match.end(),
            )

            if position != -1:
                endings.append(
                    position + 1
                )

        if endings:
            sentence_end = min(
                endings
            )

        context = page_text[
            sentence_start:
            sentence_end
        ].strip()

        ranges.append(
            {
                "start": start,
                "end": end,
                "context": context,
                "tokens": tokens(
                    context
                ),
            }
        )

    if not ranges:
        print(
            "Krispy promo parser: "
            "no active dated ranges"
        )
        return []

    results = []
    seen = set()

    headings = soup.find_all(
        ["h2", "h3"]
    )

    for heading in headings:
        title = " ".join(
            heading.stripped_strings
        ).strip()

        if not title:
            continue

        title_lower = (
            title.casefold()
        )

        # Ignore page-shell headings.
        if title_lower in {
            "doughnut deals",
            "krispy kreme",
            "participating krispy kreme locations",
        }:
            continue

        title_tokens = tokens(
            title
        )

        if not title_tokens:
            continue

        best = None
        best_score = 0

        for date_range in ranges:
            overlap = (
                title_tokens
                & date_range["tokens"]
            )

            score = len(
                overlap
            )

            if score > best_score:
                best = date_range
                best_score = score

        # Require at least one meaningful
        # title word to occur near the date
        # range. This prevents unrelated date
        # disclaimers from attaching to random
        # headings.
        if (
            best is None
            or best_score < 1
        ):
            continue

        key = (
            title.casefold(),
            best["start"].date(),
            best["end"].date(),
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        parent = heading.find_parent(
            ["article", "section"]
        )

        if parent is None:
            parent = heading.parent

        description = ""

        if parent is not None:
            description = " ".join(
                parent.stripped_strings
            )

        if not description:
            description = (
                best["context"]
            )

        description = (
            description[:1600]
        )

        event_title = (
            f"Krispy Kreme — {title}"
        )

        results.append(
            {
                "title": event_title,
                "description": description,
                "start_time":
                    best["start"].isoformat(),
                "end_time":
                    best["end"].isoformat(),
                "venue": None,
                "city": source.get(
                    "city",
                    "Birmingham",
                ),
                "state": source.get(
                    "state",
                    "AL",
                ),
                "url": source["url"],
            }
        )

    print(
        "Krispy promo events: "
        f"{len(results)}"
    )

    return results
# END KRISPY KREME PROMOTION PARSER


def collect_source(
    session,
    source,
):
    print()
    print(
        f"===== {source['name']} ====="
    )

    try:
        listing_html = fetch(
            session,
            source["url"],
        )

    except Exception as exc:
        print(
            f"FETCH FAILED: {exc}"
        )
        return []

    soup = BeautifulSoup(
        listing_html,
        "html.parser",
    )

    events = []

    # KRISPY KREME PROMOTION HOOK
    if (
        source.get("name")
        == "Krispy Kreme Offers"
    ):
        events.extend(
            parse_krispy_promotions(
                soup,
                source,
            )
        )

    for obj in parse_jsonld(soup):
        event = normalize_jsonld(
            obj,
            source,
            source["url"],
        )

        if event:
            events.append(event)

    links = candidate_links(
        soup,
        source["url"],
    )

    print(
        f"Detail links: {len(links)}"
    )

    for link in links:
        time.sleep(
            REQUEST_DELAY
        )

        try:
            html = fetch(
                session,
                link,
            )
        except Exception:
            continue

        detail = BeautifulSoup(
            html,
            "html.parser",
        )

        found_jsonld = False

        for obj in parse_jsonld(
            detail
        ):
            event = normalize_jsonld(
                obj,
                source,
                link,
            )

            if event:
                events.append(
                    event
                )
                found_jsonld = True

        if not found_jsonld:
            event = fallback_event(
                detail,
                source,
                link,
            )

            if event:
                events.append(
                    event
                )

    unique = {}

    for event in events:
        key = (
            event["title"].casefold(),
            event["start_time"],
            event.get("url"),
        )

        unique[key] = event

    result = list(
        unique.values()
    )

    print(
        f"30-day events discovered: "
        f"{len(result)}"
    )

    return result



# BEGIN REGIONAL SOURCE PACK
from app.collectors.regional_source_pack import (
    REGIONAL_IDS,
    REGIONAL_SOURCES,
)

# Reuse the existing event-key/upsert system.
REGISTRY_IDS.update(
    REGIONAL_IDS
)

_existing_source_names = {
    source["name"]
    for source in SOURCES
}

SOURCES.extend(
    dict(source)
    for source in REGIONAL_SOURCES
    if source["name"]
    not in _existing_source_names
)
# END REGIONAL SOURCE PACK

# BEGIN SPECIALTY SOURCE PACK
from app.collectors.specialty_source_pack import (
    SPECIALTY_SOURCES,
)

_specialty_existing_names = {
    source["name"]
    for source in SOURCES
}

SOURCES.extend(
    dict(source)
    for source in SPECIALTY_SOURCES
    if source["name"]
    not in _specialty_existing_names
)
# END SPECIALTY SOURCE PACK


def main():
    session = requests.Session()

    totals = {
        "new": 0,
        "changed": 0,
        "unchanged": 0,
    }

    with connect() as conn:
        for source in SOURCES:

            events = collect_source(
                session,
                source,
            )

            counts = {
                "new": 0,
                "changed": 0,
                "unchanged": 0,
            }

            for event in events:
                try:
                    status = upsert_event(
                        conn,
                        source,
                        event,
                    )

                except Exception as exc:
                    print(
                        "IMPORT ERROR: "
                        f"{event.get('title')} "
                        f"-> {exc}"
                    )

                    continue

                counts[status] += 1
                totals[status] += 1

            conn.commit()

            print(
                "New / changed / unchanged: "
                f"{counts['new']} / "
                f"{counts['changed']} / "
                f"{counts['unchanged']}"
            )

    print()
    print("=" * 72)
    print(
        " OFFICIAL WEB SOURCE COLLECTION COMPLETE"
    )
    print("=" * 72)

    for key, value in totals.items():
        print(
            f"{key.title():10}: {value}"
        )


if __name__ == "__main__":
    main()
