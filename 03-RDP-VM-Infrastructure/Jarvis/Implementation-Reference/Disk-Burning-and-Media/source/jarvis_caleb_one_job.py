#!/usr/bin/env python3

from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HOME = Path.home()

SOURCE_ROOT = Path(
    "/mnt/appdata/caleb-media/incoming/DVD"
)

MEDIA_ROOT = (
    HOME
    / "rdp-scripts/Jarvis/media"
)

TV_WORKER_PATH = (
    MEDIA_ROOT
    / "jarvis_caleb_queue_worker.py"
)

MOVIE_WORKER_PATH = (
    MEDIA_ROOT
    / "jarvis_caleb_movie_worker.py"
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


class AdapterBlocked(RuntimeError):
    pass


def load_module(
    name: str,
    path: Path,
) -> Any:
    if not path.is_file():
        raise AdapterBlocked(
            f"Required worker is missing: {path}"
        )

    specification = (
        importlib.util.spec_from_file_location(
            name,
            path,
        )
    )

    if (
        specification is None
        or specification.loader is None
    ):
        raise AdapterBlocked(
            f"Unable to load worker: {path}"
        )

    module = importlib.util.module_from_spec(
        specification
    )

    sys.modules[name] = module
    specification.loader.exec_module(module)

    return module


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


def recursively_contains(
    value: Any,
    needle: str,
) -> bool:
    if isinstance(value, str):
        return needle in value

    if isinstance(value, dict):
        return any(
            recursively_contains(key, needle)
            or recursively_contains(child, needle)
            for key, child in value.items()
        )

    if isinstance(value, list):
        return any(
            recursively_contains(child, needle)
            for child in value
        )

    return False


def validate_source(
    source: Path,
) -> Path:
    try:
        resolved_source = source.resolve(
            strict=True
        )
        resolved_root = SOURCE_ROOT.resolve(
            strict=True
        )
    except OSError as error:
        raise AdapterBlocked(
            f"Source cannot be resolved: {error}"
        ) from error

    if not resolved_source.is_dir():
        raise AdapterBlocked(
            f"Source is not a directory: "
            f"{resolved_source}"
        )

    if (
        resolved_source != resolved_root
        and resolved_root
        not in resolved_source.parents
    ):
        raise AdapterBlocked(
            "Source is outside the authorized "
            "Caleb incoming directory."
        )

    if resolved_source.name.endswith(
        ".receiving"
    ):
        raise AdapterBlocked(
            "Source is still marked .receiving."
        )

    return resolved_source


def complete_video_ts(
    source: Path,
) -> Path | None:
    candidates: list[Path] = []

    if source.name.upper() == "VIDEO_TS":
        candidates.append(source)

    candidates.extend(
        path
        for path in source.rglob("VIDEO_TS")
        if path.is_dir()
    )

    for candidate in candidates:
        if (
            candidate
            / "VIDEO_TS.IFO"
        ).is_file():
            return candidate

    return None


def registry_gate(
    source: Path,
    retry_review: bool,
) -> None:
    source_text = str(source)

    tv_registry = load_json(
        TV_REGISTRY,
        {},
    )

    movie_registry = load_json(
        MOVIE_REGISTRY,
        {},
    )

    if recursively_contains(
        tv_registry.get("passed", {}),
        source_text,
    ):
        raise AdapterBlocked(
            "Source is already recorded as "
            "successfully processed."
        )

    if recursively_contains(
        movie_registry.get("processed", {}),
        source_text,
    ):
        raise AdapterBlocked(
            "Source is already recorded as "
            "a processed movie."
        )

    if (
        recursively_contains(
            tv_registry.get("failed", {}),
            source_text,
        )
        and not retry_review
    ):
        raise AdapterBlocked(
            "Source is recorded in the review/"
            "failed registry. Use --retry-review "
            "only after approving a retry."
        )


def movie_profile(
    worker: Any,
    source: Path,
) -> tuple[
    dict[str, Any] | None,
    dict[str, Any],
]:
    configuration = worker.load_json(
        worker.PROFILE_FILE,
        {},
    )

    defaults = configuration.get(
        "defaults",
        {},
    )

    profiles = configuration.get(
        "movies",
        [],
    )

    profile = worker.recognize_movie(
        source.name,
        profiles,
    )

    return profile, defaults


def run_movie(
    worker: Any,
    source: Path,
    profile: dict[str, Any],
    defaults: dict[str, Any],
    dry_run: bool,
) -> int:
    video_ts = worker.find_video_ts(
        source
    )

    if video_ts is None:
        raise AdapterBlocked(
            "Complete VIDEO_TS structure "
            "was not found."
        )

    registry = worker.load_json(
        worker.REGISTRY_FILE,
        {
            "version": 1,
            "processed": {},
        },
    )

    processed = registry.setdefault(
        "processed",
        {},
    )

    key = worker.source_key(source)

    prior = processed.get(key, {})

    if prior.get("status") in {
        "IMPORTED",
        "ALREADY_IMPORTED",
    }:
        raise AdapterBlocked(
            "Movie source is already recorded "
            "as imported."
        )

    existing = [
        path
        for path in worker.destination_candidates(
            profile,
            defaults,
        )
        if path.is_file()
    ]

    if existing:
        print(
            "SKIP: Destination already exists:"
        )
        print(existing[0])
        return 0

    command = worker.build_command(
        video_ts,
        profile,
        defaults,
    )

    print("Route: Caleb movie")
    print(f"Source: {source}")
    print(f"Title:  {profile['title']}")
    print(
        "Command: "
        + " ".join(
            repr(part)
            for part in command
        )
    )

    if dry_run:
        print(
            "DRY RUN: Movie pipeline was not started."
        )
        return 0

    result = subprocess.run(
        command,
        input="YES\n",
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise AdapterBlocked(
            "Movie pipeline returned code "
            f"{result.returncode}."
        )

    created = [
        path
        for path in worker.destination_candidates(
            profile,
            defaults,
        )
        if path.is_file()
    ]

    if not created:
        raise AdapterBlocked(
            "Movie pipeline exited successfully, "
            "but no destination file was found."
        )

    destination = sorted(
        created,
        key=lambda path:
            path.stat().st_mtime,
    )[-1]

    processed[key] = {
        "status": "IMPORTED",
        "source": str(source),
        "video_ts": str(video_ts),
        "title": profile["title"],
        "year": profile.get("year"),
        "destination": str(destination),
        "recorded_at": (
            datetime.now(timezone.utc)
            .isoformat()
        ),
        "source_preserved": True,
    }

    worker.save_json(
        worker.REGISTRY_FILE,
        registry,
    )

    print(
        f"PASS: Movie imported to {destination}"
    )

    return 0


def extract_jobs(
    value: Any,
) -> list[dict[str, Any]]:
    if isinstance(value, list):
        if all(
            isinstance(item, dict)
            for item in value
        ):
            return value

        for item in value:
            found = extract_jobs(item)

            if found:
                return found

    if isinstance(value, tuple):
        for item in value:
            found = extract_jobs(item)

            if found:
                return found

    if isinstance(value, dict):
        jobs = value.get("jobs")

        if isinstance(jobs, list):
            return [
                item
                for item in jobs
                if isinstance(item, dict)
            ]

    return []


def discover_tv_jobs(
    worker: Any,
    registry: dict[str, Any],
) -> list[dict[str, Any]]:
    signature = inspect.signature(
        worker.discover_jobs
    )

    parameter_count = len(
        signature.parameters
    )

    if parameter_count == 0:
        result = worker.discover_jobs()

    elif parameter_count == 1:
        result = worker.discover_jobs(
            registry
        )

    elif parameter_count == 2:
        configuration = worker.load_json(
            worker.PROFILE_FILE,
            {},
        )

        if not isinstance(configuration, dict):
            raise AdapterBlocked(
                "TV profile configuration is not "
                "a JSON object."
            )

        profiles = configuration.get(
            "profiles",
            [],
        )

        if not isinstance(profiles, list):
            raise AdapterBlocked(
                "TV profile configuration does not "
                "contain a profiles list."
            )

        # registry_gate() has already blocked ordinary
        # failed jobs. Reaching this point with a failed
        # source therefore means --retry-review was
        # explicitly approved.
        #
        # Clear failed only in this temporary copy so
        # discover_jobs() can rediscover the requested
        # source. The real registry is never changed.
        discovery_registry = dict(registry)
        discovery_registry["failed"] = {}

        result = worker.discover_jobs(
            profiles,
            discovery_registry,
        )

    else:
        raise AdapterBlocked(
            "Unsupported discover_jobs contract: "
            f"{signature}"
        )

    jobs = extract_jobs(result)

    if not jobs:
        raise AdapterBlocked(
            "TV worker returned no discoverable jobs."
        )

    return jobs


def job_source(
    job: dict[str, Any],
) -> Path | None:
    for key in (
        "folder",
        "source",
        "source_path",
        "path",
    ):
        value = job.get(key)

        if value:
            try:
                return Path(value).resolve()
            except OSError:
                return Path(value)

    return None


def run_tv(
    worker: Any,
    source: Path,
    dry_run: bool,
) -> int:
    registry = worker.load_json(
        worker.REGISTRY_FILE,
        {
            "version": 1,
            "passed": {},
            "failed": {},
        },
    )

    jobs = discover_tv_jobs(
        worker,
        registry,
    )

    selected = next(
        (
            job
            for job in jobs
            if job_source(job) == source
        ),
        None,
    )

    if selected is None:
        raise AdapterBlocked(
            "The TV worker did not identify this "
            "source as an eligible TV job."
        )

    print("Route: Caleb TV")
    print(f"Source: {source}")

    for key in (
        "show",
        "season",
        "disc",
        "video_ts",
    ):
        if key in selected:
            print(
                f"{key.replace('_', ' ').title()}: "
                f"{selected[key]}"
            )

    if dry_run:
        print(
            "DRY RUN: TV worker was not started."
        )
        return 0

    signature = inspect.signature(
        worker.run_job
    )

    parameter_count = len(
        signature.parameters
    )

    if parameter_count == 2:
        result = worker.run_job(
            selected,
            registry,
        )
    elif parameter_count == 1:
        result = worker.run_job(
            selected
        )
    else:
        raise AdapterBlocked(
            "Unsupported run_job contract: "
            f"{signature}"
        )

    print(f"TV worker result: {result}")

    return (
        0
        if str(result).upper()
        in {
            "PASS",
            "SKIP",
            "ALREADY_IMPORTED",
            "DUPLICATE",
        }
        else 1
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run exactly one Caleb media job."
        )
    )

    parser.add_argument(
        "--source",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    parser.add_argument(
        "--retry-review",
        action="store_true",
    )

    arguments = parser.parse_args()

    print("=" * 72)
    print("JARVIS CALEB ONE-JOB ADAPTER")
    print("=" * 72)

    try:
        source = validate_source(
            arguments.source
        )

        registry_gate(
            source,
            arguments.retry_review,
        )

        video_ts = complete_video_ts(
            source
        )

        if video_ts is None:
            raise AdapterBlocked(
                "Complete VIDEO_TS structure "
                "was not found."
            )

        movie_worker = load_module(
            "jarvis_caleb_movie_worker_adapter",
            MOVIE_WORKER_PATH,
        )

        profile, defaults = movie_profile(
            movie_worker,
            source,
        )

        if profile is not None:
            return run_movie(
                movie_worker,
                source,
                profile,
                defaults,
                arguments.dry_run,
            )

        tv_worker = load_module(
            "jarvis_caleb_tv_worker_adapter",
            TV_WORKER_PATH,
        )

        return run_tv(
            tv_worker,
            source,
            arguments.dry_run,
        )

    except AdapterBlocked as error:
        print(f"BLOCK: {error}")
        return 2

    except Exception as error:
        print(
            "BLOCK: Unexpected "
            f"{type(error).__name__}: {error}"
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
