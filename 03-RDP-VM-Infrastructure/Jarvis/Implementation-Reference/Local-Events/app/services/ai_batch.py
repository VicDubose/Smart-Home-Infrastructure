from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import argparse
import fcntl
import json
import re
import subprocess
import sys

from app.services.ai_worker import (
    AIValidationError,
    MODEL,
    request_event_analysis,
)
from app.services.database import connect


ROOT = Path(
    "/mnt/appdata/ha-services/local-events"
)

LOCK_PATH = (
    ROOT / "state/ai-batch.lock"
)

TZ = ZoneInfo(
    "America/Chicago"
)

AI_VERSION = "gemma3-1b-event-v1"

T1000_VM = "T1000-Topology"

OLLAMA_BIN = Path(
    "/usr/local/bin/ollama"
)


class ResourceBusy(RuntimeError):
    pass


FOOD_RE = re.compile(
    r"\b("
    r"food trucks?|"
    r"food vendors?|"
    r"farmers? markets?|"
    r"ramen|"
    r"restaurants?|"
    r"tastings?|"
    r"cooking|"
    r"brunch|"
    r"food festivals?|"
    r"snacks?|"
    r"tea|"
    r"coffee|"
    r"beer|"
    r"wine|"
    r"rum|"
    r"cocktails?|"
    r"brewery|"
    r"breweries|"
    r"cider|"
    r"desserts?|"
    r"baking"
    r")\b",
    re.I,
)

FAMILY_RE = re.compile(
    r"\b("
    r"all ages|"
    r"all-ages|"
    r"family friendly|"
    r"family-friendly|"
    r"family fun|"
    r"family event|"
    r"families|"
    r"kids?|"
    r"children|"
    r"childrens?|"
    r"youth|"
    r"playdate|"
    r"play date"
    r")\b",
    re.I,
)

FREE_RE = re.compile(
    r"\b("
    r"free admission|"
    r"admission is free|"
    r"free event|"
    r"free to attend|"
    r"free entry|"
    r"no admission fee|"
    r"no cost"
    r")\b",
    re.I,
)

def now_iso():
    return datetime.now(
        TZ
    ).isoformat(
        timespec="seconds"
    )


def command_output(command):
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )

    return (
        result.returncode,
        result.stdout.strip(),
    )


def t1000_state():
    code, output = command_output(
        [
            "virsh",
            "-c",
            "qemu:///system",
            "domstate",
            T1000_VM,
        ]
    )

    if code != 0:
        raise ResourceBusy(
            "Unable to determine T1000 state: "
            + output
        )

    return output.casefold()


def loaded_models():
    code, output = command_output(
        [
            str(OLLAMA_BIN),
            "ps",
        ]
    )

    if code != 0:
        raise ResourceBusy(
            "Unable to query Ollama: "
            + output
        )

    models = []

    lines = output.splitlines()

    for line in lines[1:]:
        line = line.strip()

        if not line:
            continue

        models.append(
            line.split()[0]
        )

    return models


def assert_resources():
    state = t1000_state()

    if state != "shut off":
        raise ResourceBusy(
            f"{T1000_VM} is {state}; "
            "AI batch will not run."
        )

    models = loaded_models()

    competing = [
        model
        for model in models
        if model != MODEL
    ]

    if competing:
        raise ResourceBusy(
            "Another Ollama model is active: "
            + ", ".join(competing)
        )


def unload_phi3():
    subprocess.run(
        [
            str(OLLAMA_BIN),
            "stop",
            MODEL,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def event_payload(row):
    return {
        "title":
            row["title"],

        "description":
            row["description"],

        "venue":
            row["venue"],

        "city":
            row["city"],

        "state":
            row["state"],

        "source":
            row["source_name"],
    }


def dedupe_list(values):
    output = []
    seen = set()

    for value in values:
        if not value:
            continue

        key = str(
            value
        ).casefold()

        if key in seen:
            continue

        seen.add(
            key
        )

        output.append(
            value
        )

    return output


def deterministic_postprocess(
    analysis,
    event,
):
    data = analysis.model_dump()

    text = " ".join(
        str(
            event.get(field)
            or ""
        )
        for field in (
            "title",
            "description",
            "venue",
        )
    )

    # These three values describe explicit,
    # source-supported facts. Python owns them.
    #
    # Phi-3 may suggest them, but absence of
    # contrary information is never sufficient
    # evidence.
    # Preserve logical consistency between the
    # AI category and deterministic fact flags.
    #
    # A primary food classification necessarily
    # means the event is food-related.
    food_explicit = bool(
        FOOD_RE.search(text)
    ) or (
        data.get("primary_category")
        == "food"
    )

    # Some family-oriented branded promotions
    # don't literally contain words like "kids"
    # or "family". Recognize strong family-IP
    # evidence, while allowing explicit adult
    # restrictions to override it.
    adult_only_explicit = bool(
        re.search(
            r"\b(?:18\+|21\+|adults? only|adult[- ]only)\b",
            text,
            re.IGNORECASE,
        )
    )

    family_brand_explicit = bool(
        re.search(
            (
                r"\b(?:"
                r"pok[eé]mon|"
                r"lego|"
                r"disney|"
                r"pixar|"
                r"nintendo|"
                r"bluey|"
                r"paw patrol|"
                r"sesame street|"
                r"hello kitty|"
                r"minecraft"
                r")\b"
            ),
            text,
            re.IGNORECASE,
        )
    )

    family_explicit = (
        bool(
            FAMILY_RE.search(text)
        )
        or (
            family_brand_explicit
            and not adult_only_explicit
        )
    )

    free_explicit = bool(
        FREE_RE.search(text)
    )

    # Nightlife is an interpretive category,
    # but preserve it only when the source text
    # actually contains nightlife evidence.
    nightlife_explicit = bool(
        re.search(
            (
                r"\b(?:"
                r"nightlife|"
                r"nightclub|"
                r"night club|"
                r"bar|"
                r"pub|"
                r"brewery|"
                r"taproom|"
                r"cocktails?|"
                r"dj|"
                r"late[- ]night|"
                r"18\+|"
                r"21\+|"
                r"adults? only"
                r")\b"
            ),
            text,
            re.IGNORECASE,
        )
    )

    data["food_related"] = (
        food_explicit
    )

    data["family_friendly"] = (
        family_explicit
    )

    data["free_event"] = (
        free_explicit
    )

    # Keep seasonal output logically consistent.
    if not data.get(
        "seasonal_event",
        False,
    ):
        data[
            "seasonal_event"
        ] = False

        data[
            "seasonal_theme"
        ] = "none"

        data[
            "seasonal_confidence_score"
        ] = 0

    elif data.get(
        "seasonal_theme"
    ) == "none":
        data[
            "seasonal_event"
        ] = False

        data[
            "seasonal_confidence_score"
        ] = 0

    secondary = dedupe_list(
        data.get(
            "secondary_categories",
            [],
        )
    )

    primary = data[
        "primary_category"
    ]

    secondary = [
        category
        for category in secondary
        if category != primary
    ]

    # An AI-generated nightlife classification
    # requires actual nightlife evidence.
    if not nightlife_explicit:
        secondary = [
            category
            for category in secondary
            if category != "nightlife"
        ]

    # Don't preserve AI-generated factual
    # category hints when the source text
    # doesn't support the associated fact.
    if not food_explicit:
        secondary = [
            category
            for category in secondary
            if category != "food"
        ]

    if not family_explicit:
        secondary = [
            category
            for category in secondary
            if category != "family"
        ]

    if (
        food_explicit
        and primary != "food"
        and "food" not in secondary
    ):
        secondary.append(
            "food"
        )

    if (
        family_explicit
        and primary != "family"
        and "family" not in secondary
    ):
        secondary.append(
            "family"
        )

    data[
        "secondary_categories"
    ] = secondary[:5]

    data[
        "keywords"
    ] = dedupe_list(
        data.get(
            "keywords",
            [],
        )
    )[:12]

    return data


def recover_interrupted_jobs(
    conn,
):
    cursor = conn.execute(
        """
        UPDATE ai_jobs
        SET
            status = 'pending',
            started_at = NULL,
            error =
                'Recovered from interrupted AI batch.'
        WHERE status = 'running'
          AND job_type = 'classify_event'
        """
    )

    conn.commit()

    return cursor.rowcount


def pending_jobs(
    conn,
    limit=None,
):
    sql = """
        SELECT
            j.id AS job_id,
            j.event_id,
            j.retries,

            e.title,
            e.description,
            e.venue,
            e.city,
            e.state,
            e.source_name,
            e.tier,
            e.distance_miles

        FROM ai_jobs j

        JOIN events e
          ON e.id = j.event_id

        WHERE
            j.status = 'pending'
            AND j.job_type = 'classify_event'
            AND e.canonical = 1
            AND e.active = 1

        ORDER BY j.id
    """

    params = []

    if limit is not None:
        sql += " LIMIT ?"
        params.append(
            limit
        )

    return conn.execute(
        sql,
        params,
    ).fetchall()


def mark_running(
    conn,
    job_id,
):
    conn.execute(
        """
        UPDATE ai_jobs
        SET
            status = 'running',
            started_at = ?,
            completed_at = NULL,
            error = NULL
        WHERE id = ?
        """,
        (
            now_iso(),
            job_id,
        ),
    )

    conn.commit()


def return_to_pending(
    conn,
    job_id,
    error,
):
    conn.execute(
        """
        UPDATE ai_jobs
        SET
            status = 'pending',
            started_at = NULL,
            error = ?
        WHERE id = ?
        """,
        (
            str(error)[:1000],
            job_id,
        ),
    )

    conn.commit()


def mark_failed(
    conn,
    job_id,
    error,
    raw_response,
):
    conn.execute(
        """
        UPDATE ai_jobs
        SET
            status = 'failed',
            completed_at = ?,
            error = ?,
            raw_response = ?
        WHERE id = ?
        """,
        (
            now_iso(),
            str(error)[:1000],
            raw_response,
            job_id,
        ),
    )

    conn.commit()


def increment_retry(
    conn,
    job_id,
):
    conn.execute(
        """
        UPDATE ai_jobs
        SET retries = retries + 1
        WHERE id = ?
        """,
        (
            job_id,
        ),
    )

    conn.commit()


def save_success(
    conn,
    row,
    data,
    raw_response,
):
    conn.execute(
        """
        UPDATE events
        SET
            clean_title = ?,
            primary_category = ?,
            secondary_categories = ?,
            keywords = ?,
            family_friendly = ?,
            food_related = ?,
            free_event = ?,
            seasonal_event = ?,
            seasonal_theme = ?,
            seasonal_confidence = ?,
            personal_interest = ?,
            ai_confidence = ?,
            ai_rationale = ?,
            ai_processed = 1,
            ai_version = ?,
            ai_updated_at = ?
        WHERE id = ?
        """,
        (
            data[
                "clean_title"
            ],

            data[
                "primary_category"
            ],

            json.dumps(
                data[
                    "secondary_categories"
                ]
            ),

            json.dumps(
                data[
                    "keywords"
                ]
            ),

            int(
                data[
                    "family_friendly"
                ]
            ),

            int(
                data[
                    "food_related"
                ]
            ),

            int(
                data[
                    "free_event"
                ]
            ),

            int(
                data[
                    "seasonal_event"
                ]
            ),

            data[
                "seasonal_theme"
            ],

            int(
                data[
                    "seasonal_confidence_score"
                ]
            ),

            int(
                data[
                    "interest_score"
                ]
            ),

            int(
                data[
                    "confidence_score"
                ]
            ),

            data[
                "rationale"
            ],

            AI_VERSION,

            now_iso(),

            row[
                "event_id"
            ],
        ),
    )

    conn.execute(
        """
        UPDATE ai_jobs
        SET
            status = 'completed',
            completed_at = ?,
            raw_response = ?,
            error = NULL
        WHERE id = ?
        """,
        (
            now_iso(),
            raw_response,
            row[
                "job_id"
            ],
        ),
    )

    conn.commit()


def process_job(
    conn,
    row,
    keep_alive,
):
    job_id = row[
        "job_id"
    ]

    mark_running(
        conn,
        job_id,
    )

    event = event_payload(
        row
    )

    raw_response = None
    last_error = None

    for attempt in range(
        1,
        3,
    ):
        assert_resources()

        try:
            (
                analysis,
                raw_response,
            ) = request_event_analysis(
                event,
                keep_alive=keep_alive,
            )

            data = (
                deterministic_postprocess(
                    analysis,
                    event,
                )
            )

            save_success(
                conn,
                row,
                data,
                raw_response,
            )

            return (
                True,
                data,
            )

        except ResourceBusy:
            raise

        except Exception as exc:
            last_error = exc

            if isinstance(
                exc,
                AIValidationError,
            ):
                raw_response = (
                    exc.raw_output
                )

            if attempt == 1:
                increment_retry(
                    conn,
                    job_id,
                )

                print(
                    "    RETRY: "
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

                continue

    mark_failed(
        conn,
        job_id,
        last_error,
        raw_response,
    )

    return (
        False,
        last_error,
    )


def acquire_lock():
    LOCK_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    handle = LOCK_PATH.open(
        "w",
        encoding="utf-8",
    )

    try:
        fcntl.flock(
            handle,
            fcntl.LOCK_EX
            | fcntl.LOCK_NB,
        )

    except BlockingIOError:
        raise SystemExit(
            "BLOCK: another Local Events "
            "AI batch is already running."
        )

    handle.write(
        str(
            Path(
                "/proc/self"
            ).resolve()
        )
        + "\n"
    )

    handle.flush()

    return handle


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Process pending Local Events "
            "Phi-3 classification jobs."
        )
    )

    parser.add_argument(
        "--execute",
        action="store_true",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--keep-alive",
        default="10m",
    )

    args = parser.parse_args()

    lock = acquire_lock()

    try:
        assert_resources()

        with connect() as conn:
            recovered = (
                recover_interrupted_jobs(
                    conn
                )
            )

            rows = pending_jobs(
                conn,
                limit=args.limit,
            )

            print(
                "=" * 78
            )

            print(
                " LOCAL EVENTS — GEMMA 3 1B AI BATCH"
            )

            print(
                "=" * 78
            )

            print(
                f"Model:          {MODEL}"
            )

            print(
                f"AI version:     {AI_VERSION}"
            )

            print(
                "T1000:          shut off"
            )

            print(
                f"Jobs selected:  {len(rows)}"
            )

            print(
                f"Recovered jobs: {recovered}"
            )

            print(
                f"Mode:           "
                f"{'EXECUTE' if args.execute else 'DRY RUN'}"
            )

            print(
                "=" * 78
            )

            if not rows:
                print(
                    "No pending canonical jobs."
                )

                return 0

            if not args.execute:
                print()

                for row in rows[:20]:
                    print(
                        f"#{row['job_id']:03} "
                        f"event #{row['event_id']:03} "
                        f"{row['title']}"
                    )

                return 0

            completed = 0
            failed = 0

            for index, row in enumerate(
                rows,
                1,
            ):
                print()
                print(
                    f"[{index:02}/{len(rows):02}] "
                    f"job #{row['job_id']} "
                    f"event #{row['event_id']}"
                )

                print(
                    f"    {row['title']}"
                )

                try:
                    success, result = (
                        process_job(
                            conn,
                            row,
                            args.keep_alive,
                        )
                    )

                except ResourceBusy as exc:
                    return_to_pending(
                        conn,
                        row[
                            "job_id"
                        ],
                        exc,
                    )

                    print()
                    print(
                        "BLOCK: resource state changed."
                    )

                    print(
                        str(exc)
                    )

                    print(
                        "Current job returned to pending."
                    )

                    return 2

                if success:
                    completed += 1

                    print(
                        "    PASS"
                        f" | {result['primary_category']}"
                        f" | interest="
                        f"{result['interest_score']}"
                        f" | confidence="
                        f"{result['confidence_score']}"
                    )

                else:
                    failed += 1

                    print(
                        "    FAILED: "
                        f"{result}"
                    )

            print()
            print(
                "=" * 78
            )

            print(
                f"Completed: {completed}"
            )

            print(
                f"Failed:    {failed}"
            )

            print(
                "=" * 78
            )

            return (
                0
                if failed == 0
                else 1
            )

    finally:
        if args.execute:
            unload_phi3()

        lock.close()


if __name__ == "__main__":
    sys.exit(
        main()
    )
