#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


HOME = Path.home()

DEFAULT_CONFIG = (
    HOME
    / "Jarvis/config/media-priority-layout.env"
)

CALEB_ADAPTER = (
    HOME
    / "rdp-scripts/Jarvis/media/"
      "jarvis_caleb_one_job.py"
)

BLURAY_ADAPTER = (
    HOME
    / "rdp-scripts/Jarvis/media/"
      "jarvis_bluray_one_job.py"
)


def now() -> dt.datetime:
    return dt.datetime.now().astimezone()


def now_text() -> str:
    return now().isoformat(
        timespec="seconds"
    )


def stamp() -> str:
    return now().strftime(
        "%Y%m%d-%H%M%S"
    )


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
            parsed = shlex.split(
                raw_value
            )
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


def load_json(
    path: Path,
) -> dict[str, Any] | None:
    try:
        value = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ):
        return None

    if not isinstance(
        value,
        dict,
    ):
        return None

    return value


def atomic_json_write(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

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


def atomic_text_write(
    path: Path,
    value: str,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_name(
        f".{path.name}.tmp-{os.getpid()}"
    )

    temporary.write_text(
        value,
        encoding="utf-8",
    )

    os.replace(
        temporary,
        path,
    )


def nonblocking_lock_state(
    path: Path,
) -> str:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open("a+") as handle:
        try:
            fcntl.flock(
                handle.fileno(),
                fcntl.LOCK_EX
                | fcntl.LOCK_NB,
            )
        except BlockingIOError:
            return "busy"

        fcntl.flock(
            handle.fileno(),
            fcntl.LOCK_UN,
        )

    return "free"


def active_items(
    active_root: Path,
) -> list[str]:
    if not active_root.is_dir():
        return []

    try:
        return sorted(
            item.name
            for item in active_root.iterdir()
            if not item.name.startswith(".")
        )
    except OSError:
        return ["<unable-to-read>"]


def cooldown_status(
    state_root: Path,
    cooldown_seconds: int,
) -> dict[str, Any]:
    marker = (
        state_root
        / "last_validation_finished_at"
    )

    if not marker.is_file():
        return {
            "eligible": True,
            "remaining_seconds": 0,
            "last_finished_at": None,
            "marker": str(marker),
        }

    try:
        text = marker.read_text(
            encoding="utf-8"
        ).strip()

        finished = dt.datetime.fromisoformat(
            text
        )

        if finished.tzinfo is None:
            finished = finished.replace(
                tzinfo=now().tzinfo
            )

        age = max(
            0,
            int(
                (
                    now()
                    - finished.astimezone(
                        now().tzinfo
                    )
                ).total_seconds()
            ),
        )

        remaining = max(
            0,
            cooldown_seconds - age,
        )

        return {
            "eligible": remaining == 0,
            "remaining_seconds": remaining,
            "last_finished_at":
                finished.isoformat(),
            "marker": str(marker),
        }

    except (
        OSError,
        ValueError,
    ) as error:
        return {
            "eligible": False,
            "remaining_seconds":
                cooldown_seconds,
            "last_finished_at": None,
            "marker": str(marker),
            "error": str(error),
        }


def resolved_job_type(job: dict[str, Any], fallback: str = "") -> str:
    """
    Resolve both legacy and canonical Jarvis manifest types.

    Legacy manifests use job_type, while canonical manifests use source and
    retain the old job_type under legacy for compatibility.
    """

    legacy = job.get("legacy")

    if not isinstance(legacy, dict):
        legacy = {}

    source_map = {
        "local_bluray": "local-bluray",
        "local_dvd": "local-dvd",
        "caleb_remote": "caleb-remote",
        "local_audio_cd": "local-audio-cd",
        "local_data_disc": "local-data-disc",
    }

    return str(
        job.get("job_type")
        or legacy.get("job_type")
        or source_map.get(job.get("source"))
        or fallback
    )


def discover_lane(
    lane_name: str,
    lane_root: Path,
    default_priority: int,
) -> tuple[
    dict[str, Any],
    list[dict[str, Any]],
]:
    report: dict[str, Any] = {
        "name": lane_name,
        "path": str(lane_root),
        "exists": lane_root.is_dir(),
        "items_seen": 0,
        "ready": 0,
        "receiving": 0,
        "invalid": 0,
    }

    jobs: list[dict[str, Any]] = []

    if not lane_root.is_dir():
        return report, jobs

    try:
        entries = sorted(
            lane_root.iterdir(),
            key=lambda path:
                path.name.casefold(),
        )
    except OSError as error:
        report["error"] = str(error)
        return report, jobs

    for job_directory in entries:
        if not job_directory.is_dir():
            continue

        report["items_seen"] += 1

        if job_directory.name.endswith(
            ".receiving"
        ):
            report["receiving"] += 1
            continue

        manifest_path = (
            job_directory
            / "job.json"
        )

        manifest = load_json(
            manifest_path
        )

        if manifest is None:
            report["invalid"] += 1
            continue

        if manifest.get("state") != "ready":
            report["invalid"] += 1
            continue

        job_type = resolved_job_type(
            manifest,
            lane_name,
        )

        executable = (
            (
                lane_name == "caleb-remote"
                and job_type == "caleb-remote"
                and CALEB_ADAPTER.is_file()
            )
            or (
                lane_name == "local-bluray"
                and job_type == "local-bluray"
                and BLURAY_ADAPTER.is_file()
            )
        )

        priority = int(
            manifest.get(
                "priority",
                default_priority,
            )
        )

        registered_at = str(
            manifest.get(
                "registered_at",
                "",
            )
        )

        source_path = manifest.get(
            "source_path"
        )

        jobs.append(
            {
                "lane": lane_name,
                "job_id": str(
                    manifest.get(
                        "job_id",
                        job_directory.name,
                    )
                ),
                "job_directory":
                    str(job_directory),
                "manifest_path":
                    str(manifest_path),
                "job_type": job_type,
                "source_path":
                    str(source_path)
                    if source_path
                    else None,
                "priority": priority,
                "registered_at":
                    registered_at,
                "executable": executable,
                "manifest": manifest,
            }
        )

        report["ready"] += 1

    return report, jobs


def final_roots(
    config: dict[str, str],
    active_root: Path,
) -> dict[str, Path]:
    parent = active_root.parent

    return {
        "finished": Path(
            config.get(
                "VALIDATION_FINISHED",
                str(parent / "finished"),
            )
        ),
        "review": Path(
            config.get(
                "VALIDATION_REVIEW",
                str(parent / "review"),
            )
        ),
        "blocked": Path(
            config.get(
                "VALIDATION_BLOCKED",
                str(parent / "blocked"),
            )
        ),
        "rerip": Path(
            config.get(
                "VALIDATION_RERIP",
                str(parent / "rerip"),
            )
        ),
        "duplicate": Path(
            config.get(
                "VALIDATION_DUPLICATE",
                str(parent / "duplicate"),
            )
        ),
    }


def unique_destination(
    root: Path,
    name: str,
) -> Path:
    candidate = root / name

    if not candidate.exists():
        return candidate

    return (
        root
        / f"{name}-{stamp()}"
    )


def classify_result(
    return_code: int,
    output: str,
) -> str:
    normalized = output.casefold()

    duplicate_phrases = (
        "already recorded",
        "already processed",
        "already imported",
        "destination already exists",
        "duplicate",
        "no rip needed",
    )

    if (
        return_code in {0, 2}
        and any(
            phrase in normalized
            for phrase in duplicate_phrases
        )
    ):
        return "duplicate"

    if return_code == 0:
        return "finished"

    if return_code == 2:
        return "blocked"

    if return_code == 4:
        return "rerip"

    return "review"


def job_command(
    job: dict[str, Any],
) -> list[str]:
    source_path = job.get(
        "source_path"
    )

    if not source_path:
        raise RuntimeError(
            "Selected job has no source_path."
        )

    job_type = resolved_job_type(job)

    if job_type == "caleb-remote":
        adapter = CALEB_ADAPTER
    elif job_type == "local-bluray":
        adapter = BLURAY_ADAPTER
    else:
        raise RuntimeError(
            f"Unsupported executable job type: {job_type}"
        )

    if not adapter.is_file():
        raise RuntimeError(
            f"Job adapter is missing: {adapter}"
        )

    command = [
        sys.executable,
        "-u",
        str(adapter),
        "--source",
        str(source_path),
    ]

    manifest = job.get("manifest")
    retry_review = bool(job.get("retry_review"))

    if isinstance(manifest, dict):
        retry_review = (
            retry_review
            or bool(manifest.get("retry_review"))
        )

    if retry_review:
        command.append("--retry-review")

    return command


def execute_job(
    job: dict[str, Any],
    active_root: Path,
    result_roots: dict[str, Path],
    state_root: Path,
) -> dict[str, Any]:
    original = Path(
        job["job_directory"]
    )

    active_destination = (
        active_root
        / original.name
    )

    if active_destination.exists():
        raise RuntimeError(
            f"Active destination already exists: "
            f"{active_destination}"
        )

    os.replace(
        original,
        active_destination,
    )

    manifest_path = (
        active_destination
        / "job.json"
    )

    manifest = load_json(
        manifest_path
    ) or {}

    manifest["state"] = "validating"
    manifest["validation_started_at"] = (
        now_text()
    )

    atomic_json_write(
        manifest_path,
        manifest,
    )

    runtime_job = dict(job)

    if resolved_job_type(job) == "local-bluray":
        runtime_job["source_path"] = str(active_destination)

    command = job_command(runtime_job)

    log_path = (
        active_destination
        / "worker.log"
    )

    started = now()

    with log_path.open(
        "w",
        encoding="utf-8",
    ) as output:
        output.write(
            "$ "
            + " ".join(
                shlex.quote(part)
                for part in command
            )
            + "\n\n"
        )
        output.flush()

        process = subprocess.run(
            command,
            stdout=output,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )

    finished = now()

    try:
        worker_output = log_path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        worker_output = ""

    classification = classify_result(
        process.returncode,
        worker_output,
    )

    result_payload = {
        "job_id": job["job_id"],
        "job_type": job["job_type"],
        "source_path":
            job.get("source_path"),
        "command": command,
        "return_code":
            process.returncode,
        "classification":
            classification,
        "validation_started_at":
            started.isoformat(
                timespec="seconds"
            ),
        "validation_finished_at":
            finished.isoformat(
                timespec="seconds"
            ),
        "duration_seconds": round(
            (
                finished
                - started
            ).total_seconds(),
            3,
        ),
        "worker_log":
            str(log_path),
        "raw_source_preserved": True,
    }

    atomic_json_write(
        active_destination
        / "result.json",
        result_payload,
    )

    manifest["state"] = classification
    manifest["validation_finished_at"] = (
        result_payload[
            "validation_finished_at"
        ]
    )
    manifest["return_code"] = (
        process.returncode
    )

    atomic_json_write(
        manifest_path,
        manifest,
    )

    result_root = result_roots[
        classification
    ]

    result_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    final_destination = unique_destination(
        result_root,
        active_destination.name,
    )

    os.replace(
        active_destination,
        final_destination,
    )

    result_payload["final_job_path"] = str(
        final_destination
    )

    result_payload["worker_log"] = str(
        final_destination
        / "worker.log"
    )

    atomic_json_write(
        final_destination
        / "result.json",
        result_payload,
    )

    atomic_text_write(
        state_root
        / "last_validation_finished_at",
        result_payload[
            "validation_finished_at"
        ]
        + "\n",
    )

    return result_payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Dispatch exactly one Jarvis "
            "media-validation job."
        )
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
    )

    mode = parser.add_mutually_exclusive_group()

    mode.add_argument(
        "--dry-run",
        action="store_true",
    )

    mode.add_argument(
        "--execute",
        action="store_true",
    )

    arguments = parser.parse_args()

    execute = arguments.execute

    print("=" * 72)
    print("JARVIS ONE-JOB PRIORITY DISPATCHER")
    print("=" * 72)

    if not arguments.config.is_file():
        print(
            "BLOCK: Configuration is missing:"
        )
        print(arguments.config)
        return 1

    config = load_environment(
        arguments.config
    )

    required = (
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
    )

    missing = [
        key
        for key in required
        if not config.get(key)
    ]

    if missing:
        print(
            "BLOCK: Missing configuration keys: "
            + ", ".join(missing)
        )
        return 1

    active_root = Path(
        config["VALIDATION_ACTIVE"]
    )

    lock_path = Path(
        config["VALIDATION_LOCK"]
    )

    state_root = Path(
        config["STATE_ROOT"]
    )

    report_root = Path(
        config["REPORT_ROOT"]
    )

    cooldown_seconds = int(
        config["COOLDOWN_SECONDS"]
    )

    active_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    state_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    report_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    results = final_roots(
        config,
        active_root,
    )

    for root in results.values():
        root.mkdir(
            parents=True,
            exist_ok=True,
        )

    lanes = (
        (
            "local-dvd",
            Path(config["BURNER_LOCAL_DVD"]),
            100,
        ),
        (
            "local-bluray",
            Path(config["BURNER_LOCAL_BLURAY"]),
            100,
        ),
        (
            "local-audio-cd",
            Path(
                config[
                    "BURNER_LOCAL_AUDIO_CD"
                ]
            ),
            100,
        ),
        (
            "local-data-disc",
            Path(
                config[
                    "BURNER_LOCAL_DATA_DISC"
                ]
            ),
            100,
        ),
        (
            "caleb-remote",
            Path(config["BURNER_CALEB_REMOTE"]),
            70,
        ),
    )

    lane_reports: list[dict[str, Any]] = []
    jobs: list[dict[str, Any]] = []

    for lane_name, lane_root, priority in lanes:
        lane_report, lane_jobs = (
            discover_lane(
                lane_name,
                lane_root,
                priority,
            )
        )

        lane_reports.append(
            lane_report
        )

        jobs.extend(
            lane_jobs
        )

    jobs.sort(
        key=lambda job: (
            -int(job["priority"]),
            str(job["registered_at"]),
            str(job["job_id"]).casefold(),
        )
    )

    executable_jobs = [
        job
        for job in jobs
        if job["executable"]
    ]

    lock_state = nonblocking_lock_state(
        lock_path
    )

    current_active = active_items(
        active_root
    )

    cooldown = cooldown_status(
        state_root,
        cooldown_seconds,
    )

    execution_available = (
        lock_state == "free"
        and not current_active
        and cooldown["eligible"]
        and bool(executable_jobs)
    )

    selected = (
        executable_jobs[0]
        if execution_available
        else None
    )

    if lock_state != "free":
        reason = (
            "Validation lock is busy."
        )
    elif current_active:
        reason = (
            "Validation active slot is occupied."
        )
    elif not cooldown["eligible"]:
        reason = (
            "Validation cooldown has not expired."
        )
    elif not executable_jobs:
        reason = (
            "No executable READY jobs exist."
        )
    else:
        reason = (
            "Highest-priority executable job "
            "was selected."
        )

    payload: dict[str, Any] = {
        "generated_at": now_text(),
        "mode": (
            "execute"
            if execute
            else "dry-run"
        ),
        "lock_state": lock_state,
        "active_items": current_active,
        "cooldown": cooldown,
        "execution_available":
            execution_available,
        "selection_reason": reason,
        "selected_job": selected,
        "counts": {
            "all_ready_jobs": len(jobs),
            "executable_ready_jobs":
                len(executable_jobs),
            "nonexecutable_ready_jobs":
                len(jobs)
                - len(executable_jobs),
        },
        "lanes": lane_reports,
        "queue": jobs,
        "safety": {
            "legacy_caleb_scanned": False,
            "raw_media_moved": False,
            "arm_enabled": False,
            "bluray_execution_enabled":
                BLURAY_ADAPTER.is_file(),
        },
    }

    print(
        f"Mode:                 "
        f"{payload['mode']}"
    )
    print(
        f"Lock:                 "
        f"{lock_state}"
    )
    print(
        f"Active validations:   "
        f"{len(current_active)}"
    )
    print(
        f"READY jobs:           "
        f"{len(jobs)}"
    )
    print(
        f"Executable jobs:      "
        f"{len(executable_jobs)}"
    )
    print(
        f"Cooldown eligible:    "
        f"{cooldown['eligible']}"
    )
    print(
        f"Execution available:  "
        f"{execution_available}"
    )
    print(
        f"Selection:            "
        f"{reason}"
    )

    if selected:
        print(
            "Selected job:         "
            f"{selected['lane']} / "
            f"{selected['job_id']}"
        )
    else:
        print(
            "Selected job:         none"
        )

    result: dict[str, Any] | None = None

    if execute and selected:
        lock_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with lock_path.open(
            "a+"
        ) as lock_handle:
            try:
                fcntl.flock(
                    lock_handle.fileno(),
                    fcntl.LOCK_EX
                    | fcntl.LOCK_NB,
                )
            except BlockingIOError:
                print(
                    "WAIT: Validation lock became busy."
                )
                return 0

            if active_items(active_root):
                print(
                    "WAIT: Active slot became occupied."
                )
                return 0

            refreshed_cooldown = (
                cooldown_status(
                    state_root,
                    cooldown_seconds,
                )
            )

            if not refreshed_cooldown[
                "eligible"
            ]:
                print(
                    "WAIT: Cooldown became active."
                )
                return 0

            try:
                result = execute_job(
                    selected,
                    active_root,
                    results,
                    state_root,
                )
            except Exception as error:
                print(
                    "BLOCK: Dispatcher failure: "
                    f"{type(error).__name__}: "
                    f"{error}"
                )
                return 1

        payload["execution_result"] = (
            result
        )
        payload["safety"][
            "validation_started"
        ] = True

        print()
        print(
            "Result:               "
            f"{result['classification']}"
        )
        print(
            "Return code:          "
            f"{result['return_code']}"
        )
        print(
            "Final job path:       "
            f"{result['final_job_path']}"
        )

    elif execute:
        print()
        print(
            "No validation was started."
        )

    else:
        print()
        print(
            "DRY RUN: No validation "
            "was started."
        )

    report_path = (
        report_root
        / (
            "dispatch-"
            f"{stamp()}.json"
        )
    )

    latest_path = (
        report_root
        / "latest-dispatch.json"
    )

    atomic_json_write(
        report_path,
        payload,
    )

    atomic_json_write(
        latest_path,
        payload,
    )

    print(f"Report:               {report_path}")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
