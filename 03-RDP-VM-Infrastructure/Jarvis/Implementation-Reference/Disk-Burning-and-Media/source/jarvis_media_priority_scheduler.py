#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
import shlex
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = Path.home() / "Jarvis/config/media-priority-layout.env"
LEGACY_CALEB_ROOT = Path("/mnt/appdata/caleb-media/incoming/DVD")


def timestamp() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def filename_timestamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def load_environment(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, raw_value = line.split("=", 1)
        key = key.strip()
        raw_value = raw_value.strip()

        try:
            parsed = shlex.split(raw_value)
            value = parsed[0] if parsed else ""
        except ValueError:
            value = raw_value.strip('"').strip("'")

        values[key] = value

    return values


def atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary_path = Path(handle.name)

    temporary_path.replace(path)


def test_lock(lock_path: Path) -> str:
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    descriptor = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT,
        0o660,
    )

    try:
        try:
            fcntl.flock(
                descriptor,
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            return "free"
        except BlockingIOError:
            return "busy"
    finally:
        os.close(descriptor)


def active_validation_items(active_path: Path) -> list[str]:
    if not active_path.is_dir():
        return []

    return sorted(
        str(item)
        for item in active_path.iterdir()
        if not item.name.startswith(".")
    )


def cooldown_information(
    state_root: Path,
    cooldown_seconds: int,
) -> dict[str, Any]:
    state_file = state_root / "last_validation_finished_at"
    now = dt.datetime.now().astimezone()

    if not state_file.exists():
        return {
            "state_file": str(state_file),
            "last_validation_finished_at": None,
            "remaining_seconds": 0,
            "eligible": True,
        }

    raw_value = state_file.read_text(encoding="utf-8").strip()

    try:
        if raw_value.isdigit():
            finished = dt.datetime.fromtimestamp(
                int(raw_value),
                tz=now.tzinfo,
            )
        else:
            finished = dt.datetime.fromisoformat(raw_value)

            if finished.tzinfo is None:
                finished = finished.replace(tzinfo=now.tzinfo)
    except (ValueError, OSError):
        return {
            "state_file": str(state_file),
            "last_validation_finished_at": raw_value,
            "remaining_seconds": cooldown_seconds,
            "eligible": False,
            "error": "Cooldown timestamp could not be parsed.",
        }

    age_seconds = max(
        0,
        int((now - finished).total_seconds()),
    )

    remaining = max(
        0,
        cooldown_seconds - age_seconds,
    )

    return {
        "state_file": str(state_file),
        "last_validation_finished_at": finished.isoformat(
            timespec="seconds"
        ),
        "remaining_seconds": remaining,
        "eligible": remaining == 0,
    }


def make_job_id(
    source_name: str,
    path: Path,
    modified_ns: int,
) -> str:
    material = (
        f"{source_name}\0{path}\0{modified_ns}"
    ).encode("utf-8", errors="replace")

    return hashlib.sha256(material).hexdigest()[:20]


def discover_source(
    source_name: str,
    source_path: Path,
    priority: int,
    *,
    legacy: bool = False,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source_report: dict[str, Any] = {
        "name": source_name,
        "path": str(source_path),
        "priority": priority,
        "legacy": legacy,
        "exists": source_path.is_dir(),
        "items_seen": 0,
        "ready": 0,
        "receiving": 0,
        "legacy_candidates": 0,
        "errors": [],
    }

    jobs: list[dict[str, Any]] = []

    if not source_path.is_dir():
        return source_report, jobs

    try:
        items = sorted(
            source_path.iterdir(),
            key=lambda item: item.name.casefold(),
        )
    except OSError as error:
        source_report["errors"].append(str(error))
        return source_report, jobs

    for item in items:
        if item.name.startswith("."):
            continue

        source_report["items_seen"] += 1

        if item.name.endswith(".receiving"):
            state = "receiving"
            eligible = False
            source_report["receiving"] += 1
        elif legacy:
            state = "legacy_candidate"
            eligible = False
            source_report["legacy_candidates"] += 1
        else:
            state = "ready"
            eligible = True
            source_report["ready"] += 1

        try:
            stat_result = item.stat(follow_symlinks=False)
        except OSError as error:
            source_report["errors"].append(
                f"{item}: {error}"
            )
            continue

        modified = dt.datetime.fromtimestamp(
            stat_result.st_mtime,
            tz=dt.datetime.now().astimezone().tzinfo,
        )

        jobs.append(
            {
                "job_id": make_job_id(
                    source_name,
                    item,
                    stat_result.st_mtime_ns,
                ),
                "source": source_name,
                "source_path": str(source_path),
                "path": str(item),
                "name": item.name,
                "priority": priority,
                "state": state,
                "eligible": eligible,
                "item_type": (
                    "directory"
                    if item.is_dir()
                    else "file"
                ),
                "ready_since": modified.isoformat(
                    timespec="seconds"
                ),
                "modified_ns": stat_result.st_mtime_ns,
            }
        )

    return source_report, jobs


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Discover and rank Jarvis media jobs without "
            "moving or processing media."
        )
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
    )

    arguments = parser.parse_args()

    if not arguments.config.is_file():
        print(
            f"BLOCK: Configuration is missing: "
            f"{arguments.config}"
        )
        return 1

    config = load_environment(arguments.config)

    required_keys = [
        "BURNER_LOCAL_DVD",
        "BURNER_LOCAL_BLURAY",
        "BURNER_LOCAL_AUDIO_CD",
        "BURNER_LOCAL_DATA_DISC",
        "BURNER_CALEB_REMOTE",
        "VALIDATION_ACTIVE",
        "VALIDATION_LOCK",
        "COOLDOWN_SECONDS",
        "STATE_ROOT",
        "REPORT_ROOT",
    ]

    missing = [
        key
        for key in required_keys
        if not config.get(key)
    ]

    if missing:
        print(
            "BLOCK: Missing configuration keys: "
            + ", ".join(missing)
        )
        return 1

    sources = [
        (
            "local-dvd",
            Path(config["BURNER_LOCAL_DVD"]),
            100,
            False,
        ),
        (
            "local-bluray",
            Path(config["BURNER_LOCAL_BLURAY"]),
            100,
            False,
        ),
        (
            "local-audio-cd",
            Path(config["BURNER_LOCAL_AUDIO_CD"]),
            100,
            False,
        ),
        (
            "local-data-disc",
            Path(config["BURNER_LOCAL_DATA_DISC"]),
            100,
            False,
        ),
        (
            "caleb-remote",
            Path(config["BURNER_CALEB_REMOTE"]),
            70,
            False,
        ),
        (
            "legacy-caleb",
            LEGACY_CALEB_ROOT,
            70,
            True,
        ),
    ]

    source_reports: list[dict[str, Any]] = []
    jobs: list[dict[str, Any]] = []

    for source_name, source_path, priority, legacy in sources:
        source_report, discovered = discover_source(
            source_name,
            source_path,
            priority,
            legacy=legacy,
        )

        source_reports.append(source_report)
        jobs.extend(discovered)

    jobs.sort(
        key=lambda job: (
            -int(job["priority"]),
            str(job["ready_since"]),
            str(job["name"]).casefold(),
        )
    )

    eligible_jobs = [
        job for job in jobs if job["eligible"]
    ]

    receiving_jobs = [
        job
        for job in jobs
        if job["state"] == "receiving"
    ]

    legacy_candidates = [
        job
        for job in jobs
        if job["state"] == "legacy_candidate"
    ]

    validation_active_path = Path(
        config["VALIDATION_ACTIVE"]
    )

    lock_path = Path(config["VALIDATION_LOCK"])
    state_root = Path(config["STATE_ROOT"])
    report_root = Path(config["REPORT_ROOT"])

    lock_status = test_lock(lock_path)
    active_items = active_validation_items(
        validation_active_path
    )

    cooldown = cooldown_information(
        state_root,
        int(config["COOLDOWN_SECONDS"]),
    )

    execution_available = (
        lock_status == "free"
        and not active_items
        and cooldown["eligible"]
        and bool(eligible_jobs)
    )

    selected_job = (
        eligible_jobs[0]
        if execution_available
        else None
    )

    if lock_status != "free":
        selection_reason = (
            "Shared validation lock is currently busy."
        )
    elif active_items:
        selection_reason = (
            "Validation active slot is occupied."
        )
    elif not cooldown["eligible"]:
        selection_reason = (
            "Validation cooldown has not expired."
        )
    elif not eligible_jobs:
        selection_reason = (
            "No READY jobs exist in the new staging areas."
        )
    else:
        selection_reason = (
            "Highest-priority READY job identified."
        )

    payload: dict[str, Any] = {
        "generated_at": timestamp(),
        "mode": "dry-run",
        "configuration": str(arguments.config),
        "lock_state": lock_status,
        "active_validation_items": active_items,
        "cooldown": cooldown,
        "execution_available": execution_available,
        "selection_reason": selection_reason,
        "selected_job": selected_job,
        "counts": {
            "all_items": len(jobs),
            "eligible_ready_jobs": len(eligible_jobs),
            "receiving_jobs": len(receiving_jobs),
            "legacy_candidates": len(legacy_candidates),
        },
        "sources": source_reports,
        "queue": jobs,
        "safety": {
            "media_moved": False,
            "validation_started": False,
            "library_modified": False,
            "legacy_candidates_executable": False,
        },
    }

    report_path = (
        report_root
        / f"queue-snapshot-{filename_timestamp()}.json"
    )

    latest_path = report_root / "latest.json"

    atomic_json_write(report_path, payload)
    atomic_json_write(latest_path, payload)

    print("=" * 64)
    print("JARVIS MEDIA PRIORITY SCHEDULER — DRY RUN")
    print("=" * 64)
    print(f"Generated:              {payload['generated_at']}")
    print(f"Shared lock:            {lock_status}")
    print(f"Active validations:     {len(active_items)}")
    print(f"READY staging jobs:     {len(eligible_jobs)}")
    print(f"Legacy Caleb candidates:{len(legacy_candidates)}")
    print(f"Receiving jobs:         {len(receiving_jobs)}")
    print(f"Execution available:    {execution_available}")
    print(f"Selection:              {selection_reason}")

    if selected_job:
        print(
            "Selected job:          "
            f"{selected_job['source']} / "
            f"{selected_job['name']}"
        )
    else:
        print("Selected job:          none")

    print(f"Report:                 {report_path}")
    print()
    print("DRY RUN: No media was moved or processed.")
    print("=" * 64)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
