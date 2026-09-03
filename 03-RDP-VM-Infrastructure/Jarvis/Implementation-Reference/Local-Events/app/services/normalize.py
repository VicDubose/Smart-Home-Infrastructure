from hashlib import sha256
from zoneinfo import ZoneInfo
import html
import json
import re

from dateutil import parser as date_parser


LOCAL_TZ = ZoneInfo(
    "America/Chicago"
)


def clean_text(value):
    if value is None:
        return None

    value = html.unescape(
        str(value)
    )

    value = re.sub(
        r"<[^>]+>",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    value = value.strip()

    return value or None


def parse_datetime(value):
    if not value:
        return None

    try:
        dt = date_parser.parse(
            str(value)
        )
    except Exception:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=LOCAL_TZ
        )

    return dt.astimezone(
        LOCAL_TZ
    )


def iso_datetime(value):
    dt = parse_datetime(
        value
    )

    if not dt:
        return None

    return dt.isoformat(
        timespec="seconds"
    )


def parse_city_state(value):
    value = clean_text(
        value
    )

    if not value:
        return None

    match = re.fullmatch(
        r"(.+?),\s*([A-Za-z]{2})",
        value,
    )

    if not match:
        return None

    return {
        "city": match.group(1).strip(),
        "state": match.group(2).upper(),
    }


def extract_location(
    item,
    fallback_city=None,
    fallback_state=None,
):
    location = (
        item.get("location")
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

    # ----------------------------------------
    # Plain string location
    # ----------------------------------------

    if isinstance(
        location,
        str,
    ):
        raw_location = clean_text(
            location
        )

        city_state = parse_city_state(
            raw_location
        )

        if city_state:
            return {
                "venue": None,
                "city": city_state["city"],
                "state": city_state["state"],
                "latitude": None,
                "longitude": None,
            }

        return {
            "venue": raw_location,
            "city": fallback_city,
            "state": fallback_state,
            "latitude": None,
            "longitude": None,
        }

    if not isinstance(
        location,
        dict,
    ):
        location = {}

    venue = clean_text(
        location.get("name")
    )

    address = (
        location.get("address")
        or {}
    )

    # ----------------------------------------
    # Localist/UAB remote-location pattern:
    #
    # {
    #   "@type": "Place",
    #   "address": "",
    #   "name": "Mobile, AL"
    # }
    #
    # Here "Mobile, AL" is a geographic place,
    # not a venue.
    # ----------------------------------------

    venue_city_state = (
        parse_city_state(
            venue
        )
    )

    address_is_empty = (
        address == ""
        or address == {}
        or address is None
    )

    if (
        venue_city_state
        and address_is_empty
    ):
        city = (
            venue_city_state[
                "city"
            ]
        )

        state = (
            venue_city_state[
                "state"
            ]
        )

        venue = None

    elif isinstance(
        address,
        dict,
    ):
        city = (
            clean_text(
                address.get(
                    "addressLocality"
                )
            )
            or fallback_city
        )

        state = (
            clean_text(
                address.get(
                    "addressRegion"
                )
            )
            or fallback_state
        )

    else:
        city = fallback_city
        state = fallback_state

    geo = (
        location.get("geo")
        or {}
    )

    if not isinstance(
        geo,
        dict,
    ):
        geo = {}

    try:
        latitude = float(
            geo.get("latitude")
        )
    except (
        TypeError,
        ValueError,
    ):
        latitude = None

    try:
        longitude = float(
            geo.get("longitude")
        )
    except (
        TypeError,
        ValueError,
    ):
        longitude = None

    return {
        "venue": venue,
        "city": city,
        "state": state,
        "latitude": latitude,
        "longitude": longitude,
    }


def source_identifier(item):
    candidates = [
        item.get("@id"),
        item.get("url"),
        item.get("identifier"),
    ]

    for value in candidates:

        if (
            isinstance(
                value,
                str,
            )
            and value.strip()
        ):
            return value.strip()

        if isinstance(
            value,
            dict,
        ):
            candidate = (
                value.get("value")
                or value.get("@id")
            )

            if candidate:
                return str(
                    candidate
                ).strip()

    return None


def event_key(
    source_id,
    source_event_id,
    title,
    start_time,
    venue,
):
    if source_event_id:
        raw = (
            f"{source_id}|"
            f"{source_event_id}"
        )

    else:
        raw = "|".join(
            [
                source_id,
                title or "",
                start_time or "",
                venue or "",
            ]
        )

    return sha256(
        raw.encode(
            "utf-8"
        )
    ).hexdigest()


def content_hash(record):
    significant = {
        "title":
            record.get("title"),

        "description":
            record.get("description"),

        "start_time":
            record.get("start_time"),

        "end_time":
            record.get("end_time"),

        "venue":
            record.get("venue"),

        "city":
            record.get("city"),

        "state":
            record.get("state"),

        "latitude":
            record.get("latitude"),

        "longitude":
            record.get("longitude"),

        "source_url":
            record.get("source_url"),
    }

    payload = json.dumps(
        significant,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    return sha256(
        payload.encode(
            "utf-8"
        )
    ).hexdigest()


def normalize_jsonld_event(
    source,
    item,
):
    title = clean_text(
        item.get("name")
    )

    start_time = iso_datetime(
        item.get("startDate")
    )

    if (
        not title
        or not start_time
    ):
        return None

    end_time = iso_datetime(
        item.get("endDate")
    )

    location = extract_location(
        item,
        fallback_city=source.get(
            "city"
        ),
        fallback_state=source.get(
            "state"
        ),
    )

    source_url = clean_text(
        item.get("url")
    )

    source_event_id = (
        source_identifier(
            item
        )
    )

    record = {
        "title": title,

        "description":
            clean_text(
                item.get(
                    "description"
                )
            ),

        "start_time":
            start_time,

        "end_time":
            end_time,

        "venue":
            location["venue"],

        "city":
            location["city"],

        "state":
            location["state"],

        "latitude":
            location["latitude"],

        "longitude":
            location["longitude"],

        "source_name":
            source["name"],

        "source_id":
            source["id"],

        "source_event_id":
            source_event_id,

        "source_url":
            source_url,

        "raw_json":
            json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
            ),
    }

    record["event_key"] = (
        event_key(
            source["id"],
            source_event_id,
            title,
            start_time,
            location["venue"],
        )
    )

    record["content_hash"] = (
        content_hash(
            record
        )
    )

    return record
