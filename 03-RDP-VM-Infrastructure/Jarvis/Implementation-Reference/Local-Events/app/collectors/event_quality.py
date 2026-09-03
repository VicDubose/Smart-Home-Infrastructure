from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
import re


TZ = ZoneInfo("America/Chicago")


BAD_EXACT = {
    "",
    "skip navigation",
    "skip to main content",
    "click here",
    "learn more",
    "read more",
    "view more",
    "more info",
    "get tickets",
    "buy tickets",
    "find events",
    "search",
    "events",
    "event",
    "calendar",
    "event calendar",
    "today",
    "previous events",
    "next events",
    "menu close",
    "home",
    "directions",
    "sign up",
    "subscribe",
}


BAD_PREFIXES = (
    "skip navigation",
    "skip to main",
    "private event",
    "cancelled:",
    "canceled:",
)


BAD_PATTERNS = (
    re.compile(
        r"^\s*(click|tap)\s+here\s*$",
        re.I,
    ),
    re.compile(
        r"^\s*(learn|read|view)\s+more\s*$",
        re.I,
    ),
    re.compile(
        r"^\s*(buy|get)\s+tickets?\s*$",
        re.I,
    ),
)


def _clean(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or ""),
    ).strip()


def _parse_dt(value):
    if isinstance(
        value,
        datetime,
    ):
        return value

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


def rejection_reason(
    source,
    event,
):
    title = _clean(
        event.get(
            "title",
            "",
        )
    )

    folded = title.casefold()

    if not title:
        return "blank-title"

    if folded in BAD_EXACT:
        return "ui-title"

    if any(
        folded.startswith(prefix)
        for prefix
        in BAD_PREFIXES
    ):
        return "ui/private/cancelled"

    if any(
        pattern.match(title)
        for pattern
        in BAD_PATTERNS
    ):
        return "ui-title"

    # Browser events need an actual event date.
    dt = _parse_dt(
        event.get(
            "start_time"
        )
    )

    if dt is None:
        return "missing-date"

    # Bands on the Beach is explicitly a Tuesday series.
    #
    # This blocks old historical schedule entries that the
    # generic browser parser previously interpreted as current.
    if (
        source.get("name")
        == "Bands on the Beach"
        and dt.weekday() != 1
    ):
        return "bands-not-tuesday"

    return None


def sanitize_events(
    source,
    events,
):
    kept = []
    rejected = []
    seen = set()

    for event in events:

        reason = rejection_reason(
            source,
            event,
        )

        if reason:
            rejected.append(
                (
                    reason,
                    _clean(
                        event.get(
                            "title"
                        )
                    ),
                )
            )
            continue

        title = _clean(
            event.get(
                "title"
            )
        )

        dt = _parse_dt(
            event.get(
                "start_time"
            )
        )

        venue = _clean(
            event.get(
                "venue"
            )
        )

        key = (
            title.casefold(),
            (
                dt.isoformat()
                if dt
                else ""
            ),
            venue.casefold(),
        )

        if key in seen:
            rejected.append(
                (
                    "same-run-duplicate",
                    title,
                )
            )
            continue

        seen.add(
            key
        )

        event["title"] = title

        kept.append(
            event
        )

    print(
        "QUALITY GUARD: "
        f"kept={len(kept)} "
        f"rejected={len(rejected)}"
    )

    for reason, title in rejected[:15]:
        print(
            f"  REJECT "
            f"[{reason}] "
            f"{title[:90]}"
        )

    if len(rejected) > 15:
        print(
            "  ... "
            f"{len(rejected)-15} "
            "additional rejected candidates"
        )

    return kept
