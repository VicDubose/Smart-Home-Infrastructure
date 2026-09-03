#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


HOME = Path.home()

DEFAULT_CONFIG = (
    HOME
    / "Jarvis/config/media-priority-layout.env"
)

SOURCE_ROOT = Path(
    "/mnt/appdata/caleb-media/incoming/DVD"
)

ADAPTER = (
    HOME
    / "rdp-scripts/Jarvis/media/"
      "jarvis_caleb_one_job.py"
)

TV_REGISTRY = (
    HOME
    / "Jarvis/state/caleb-auto-ingest/"
      "processed_registry.json"
)

MOVIE_REGISTRY = (
    HOME
    / "Jarvis/state/caleb-movie-ingest/"
      "processed_registry.json"
)


def now_text() -> str:
    return (
        dt.datetime.now()
        .astimezone()
        .isoformat(timespec="seconds")
    )


def stamp() -> str:
    return dt.datetime.now().strftime(
        "%Y%m%d-%H%M%S"
    )


def load_json(
    path: Path,
    default: Any,
) -> Any:
    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            return json.load(handle)
    except (
        OSError,
        json.JSONDecodeError,
    ):
        return default


def load_environment(
    path: Path,
) -> dict[str, str]:
    values: dict[str, str] = {}

    for raw_line in path.read_text(
        encoding="utf-8"
    ).splitlines():
        line = raw_line.strip()

        if (
            not line
            or line.startswith("#")
            or "=" not in line
        ):
            continue

        key, raw_value = line.split(
            "=",
            1,
        )

        key = key.strip()
        raw_value = raw_value.strip()

        try:
            parsed = shlex.split(raw_value)
            value = (
                parsed[0]
                if parsed
                else ""
            )
        except ValueError:
            value = raw_value.strip(
                "\"'"
            )

        values[key] = value

    return values


def contains_text(
    value: Any,
    needle: str,
) -> bool:
    if isinstance(value, str):
        return needle in value

    if isinstance(value, dict):
        return any(
            contains_text(key, needle)
            or contains_text(child, needle)
            for key, child in value.items()
        )

    if isinstance(value, list):
        return any(
            contains_text(child, needle)
            for child in value
        )

    return False


def find_video_ts(
    source: Path,
) -> Path | None:
    candidates: list[Path] = []

    if source.name.upper() == "VIDEO_TS":
        candidates.append(source)

    try:
        candidates.extend(
            path
            for path in source.rglob(
                "VIDEO_TS"
            )
            if path.is_dir()
        )
    except OSError:
        return None

    for candidate in candidates:
        if (
            candidate
            / "VIDEO_TS.IFO"
        ).is_file():
            return candidate

    return None


def safe_name(
    value: str,
) -> str:
    cleaned = re.sub(
        r"[^A-Za-z0-9._-]+",
        "-",
        value,
    )

    cleaned = cleaned.strip(
        "._-"
    )

    return (
        cleaned[:100]
        or "caleb-job"
    )


def make_job_id(
    source: Path,
) -> str:
    digest = hashlib.sha256(
        str(source.resolve()).encode(
            "utf-8"
        )
    ).hexdigest()[:12]

    return (
        f"{safe_name(source.name)}"
        f"-{digest}"
    )


def write_json_atomic(
    path: Path,
    payload: dict[str, Any],
) -> None:
    temporary = path.with_name(
        f".{path.name}.tmp-{os.getpid()}"
    )

    temporary.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    os.replace(
        temporary,
        path,
    )



def terminal_job_path(
    job_id: str,
    roots: list[Path],
) -> Path | None:
    for root in roots:
        if not root.is_dir():
            continue

        direct = root / job_id

        if direct.is_dir():
            return direct

        matches = sorted(
            (
                path
                for path in root.glob(
                    f"{job_id}-*"
                )
                if path.is_dir()
            ),
            key=lambda path:
                path.name.casefold(),
        )

        if matches:
            return matches[-1]

    return None

def adapter_probe(
    source: Path,
) -> tuple[bool, str]:
    result = subprocess.run(
        [
            sys.executable,
            str(ADAPTER),
            "--source",
            str(source),
            "--dry-run",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=120,
    )

    output = result.stdout.strip()

    tail = "\n".join(
        output.splitlines()[-12:]
    )

    return (
        result.returncode == 0,
        tail,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Register eligible Caleb raw rips "
            "with the Jarvis priority scheduler."
        )
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
    )

    parser.add_argument(
        "--commit",
        action="store_true",
        help=(
            "Create staging job manifests. "
            "Without this flag, only report."
        ),
    )

    arguments = parser.parse_args()

    print("=" * 72)
    print("JARVIS CALEB PRIORITY REGISTRAR")
    print("=" * 72)

    if not arguments.config.is_file():
        print(
            "BLOCK: Configuration is missing:"
        )
        print(arguments.config)
        return 1

    if not SOURCE_ROOT.is_dir():
        print(
            "BLOCK: Caleb source root is missing:"
        )
        print(SOURCE_ROOT)
        return 1

    if not ADAPTER.is_file():
        print(
            "BLOCK: One-job adapter is missing:"
        )
        print(ADAPTER)
        return 1

    config = load_environment(
        arguments.config
    )

    staging_value = config.get(
        "BURNER_CALEB_REMOTE"
    )

    report_value = config.get(
        "REPORT_ROOT"
    )

    if not staging_value:
        print(
            "BLOCK: BURNER_CALEB_REMOTE "
            "is missing from configuration."
        )
        return 1

    if not report_value:
        print(
            "BLOCK: REPORT_ROOT is missing "
            "from configuration."
        )
        return 1

    staging_root = Path(
        staging_value
    )

    report_root = Path(
        report_value
    )

    validation_active_value = config.get(
        "VALIDATION_ACTIVE"
    )

    if not validation_active_value:
        print(
            "BLOCK: VALIDATION_ACTIVE is missing "
            "from configuration."
        )
        return 1

    validation_parent = Path(
        validation_active_value
    ).parent

    terminal_roots = [
        Path(
            config.get(
                "VALIDATION_FINISHED",
                str(validation_parent / "finished"),
            )
        ),
        Path(
            config.get(
                "VALIDATION_REVIEW",
                str(validation_parent / "review"),
            )
        ),
        Path(
            config.get(
                "VALIDATION_BLOCKED",
                str(validation_parent / "blocked"),
            )
        ),
        Path(
            config.get(
                "VALIDATION_RERIP",
                str(validation_parent / "rerip"),
            )
        ),
        Path(
            config.get(
                "VALIDATION_DUPLICATE",
                str(validation_parent / "duplicate"),
            )
        ),
    ]

    staging_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    report_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    tv_registry = load_json(
        TV_REGISTRY,
        {},
    )

    movie_registry = load_json(
        MOVIE_REGISTRY,
        {},
    )

    passed_records = tv_registry.get(
        "passed",
        {},
    )

    failed_records = tv_registry.get(
        "failed",
        {},
    )

    movie_records = movie_registry.get(
        "processed",
        {},
    )

    records: list[dict[str, Any]] = []

    folders = sorted(
        [
            path
            for path in SOURCE_ROOT.iterdir()
            if path.is_dir()
        ],
        key=lambda path:
            path.name.casefold(),
    )

    for source in folders:
        source_text = str(
            source.resolve()
        )

        record: dict[str, Any] = {
            "source": source_text,
            "name": source.name,
            "registered": False,
            "job_path": None,
        }

        if source.name.endswith(
            ".receiving"
        ):
            record["status"] = "RECEIVING"
            record["reason"] = (
                "Transfer is not complete."
            )

        elif contains_text(
            passed_records,
            source_text,
        ):
            record["status"] = "PROCESSED"
            record["reason"] = (
                "Recorded in the TV passed registry."
            )

        elif contains_text(
            movie_records,
            source_text,
        ):
            record["status"] = "PROCESSED"
            record["reason"] = (
                "Recorded in the movie registry."
            )

        elif contains_text(
            failed_records,
            source_text,
        ):
            record["status"] = "REVIEW"
            record["reason"] = (
                "Recorded in the TV failed registry."
            )

        else:
            video_ts = find_video_ts(
                source
            )

            if video_ts is None:
                record["status"] = "INCOMPLETE"
                record["reason"] = (
                    "Complete VIDEO_TS structure "
                    "was not found."
                )

            else:
                job_id = make_job_id(
                    source
                )

                job_path = (
                    staging_root
                    / job_id
                )

                terminal_path = terminal_job_path(
                    job_id,
                    terminal_roots,
                )

                if terminal_path is not None:
                    record["status"] = "TERMINAL"
                    record["reason"] = (
                        "A terminal job record already exists. "
                        "The source will not be registered again."
                    )
                    record["terminal_path"] = str(
                        terminal_path
                    )

                elif job_path.is_dir():
                    record["status"] = "REGISTERED"
                    record["reason"] = (
                        "The job is already waiting in "
                        "priority staging."
                    )
                    record["registered"] = True
                    record["job_path"] = str(
                        job_path
                    )

                else:
                    eligible, probe_output = (
                        adapter_probe(source)
                    )

                    record["adapter_probe"] = (
                        probe_output
                    )

                    if not eligible:
                        record["status"] = "BLOCKED"
                        record["reason"] = (
                            "The one-job adapter did not "
                            "accept this source."
                        )

                    else:
                        record["status"] = "READY"
                        record["reason"] = (
                            "Eligible for one-job dispatch."
                        )
                        record["job_path"] = str(
                            job_path
                        )

                        manifest = {
                            "version": 1,
                            "job_id": job_id,
                            "job_type": "caleb-remote",
                            "state": "ready",
                            "priority": 70,
                            "source_path": source_text,
                            "video_ts": str(
                                video_ts.resolve()
                            ),
                            "worker": str(ADAPTER),
                            "registered_at": now_text(),
                            "source_preserved": True,
                        }

                        if arguments.commit:
                            temporary = (
                                staging_root
                                / (
                                    f".{job_id}"
                                    f".receiving"
                                )
                            )

                            if temporary.exists():
                                record["status"] = "BLOCKED"
                                record["reason"] = (
                                    "An incomplete registration "
                                    "directory already exists."
                                )

                            else:
                                temporary.mkdir(
                                    parents=False,
                                    exist_ok=False,
                                )

                                write_json_atomic(
                                    temporary
                                    / "job.json",
                                    manifest,
                                )

                                os.replace(
                                    temporary,
                                    job_path,
                                )

                                record["registered"] = True
                                record["reason"] = (
                                    "Job manifest registered."
                                )


        records.append(record)

    counts = Counter(
        record["status"]
        for record in records
    )

    payload = {
        "generated_at": now_text(),
        "mode": (
            "commit"
            if arguments.commit
            else "dry-run"
        ),
        "source_root": str(
            SOURCE_ROOT
        ),
        "staging_root": str(
            staging_root
        ),
        "counts": dict(counts),
        "records": records,
        "safety": {
            "raw_media_moved": False,
            "validation_started": False,
            "library_modified": False,
        },
    }

    report_path = (
        report_root
        / (
            "caleb-registration-"
            f"{stamp()}.json"
        )
    )

    latest_path = (
        report_root
        / "latest-caleb-registration.json"
    )

    write_json_atomic(
        report_path,
        payload,
    )

    write_json_atomic(
        latest_path,
        payload,
    )

    print(f"Mode:       {payload['mode']}")
    print(f"Sources:    {len(records)}")
    print(f"Processed:  {counts.get('PROCESSED', 0)}")
    print(f"Review:     {counts.get('REVIEW', 0)}")
    print(f"Receiving:  {counts.get('RECEIVING', 0)}")
    print(f"Incomplete: {counts.get('INCOMPLETE', 0)}")
    print(f"Blocked:    {counts.get('BLOCKED', 0)}")
    print(f"Terminal:   {counts.get('TERMINAL', 0)}")
    print(f"Already staged: {counts.get('REGISTERED', 0)}")
    print(f"Ready:      {counts.get('READY', 0)}")
    print(
        "Registered: "
        f"{sum(1 for item in records if item['registered'])}"
    )
    print(f"Report:     {report_path}")
    print()

    if arguments.commit:
        print(
            "No media was moved or processed. "
            "Only job manifests may have been created."
        )
    else:
        print(
            "DRY RUN: No job manifests were created."
        )

    print("=" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
