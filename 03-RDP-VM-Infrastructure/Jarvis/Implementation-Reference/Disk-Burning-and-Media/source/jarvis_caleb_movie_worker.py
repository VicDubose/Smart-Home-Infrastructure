#!/usr/bin/env python3

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HOME = Path.home()

SOURCE_ROOT = Path("/mnt/appdata/caleb-media/incoming/DVD")
PROFILE_FILE = HOME / "Jarvis/config/caleb_movie_profiles.json"
MOVIE_PIPELINE = HOME / "rdp-scripts/Jarvis/media/jarvis_movie_dvd_ingest.py"

STATE_ROOT = HOME / "Jarvis/state/caleb-movie-ingest"
REPORT_ROOT = HOME / "Jarvis/reports/caleb-movie-ingest"
QUARANTINE_ROOT = HOME / "Jarvis/quarantine/caleb-movie-ingest"

REGISTRY_FILE = STATE_ROOT / "processed_registry.json"


def log(message: str = "") -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Unable to read JSON file {path}: {exc}") from exc


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(data, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def source_key(path: Path) -> str:
    return hashlib.sha256(str(path.resolve()).encode("utf-8")).hexdigest()[:24]


def find_video_ts(folder: Path) -> Path | None:
    if folder.name.upper() == "VIDEO_TS":
        candidate = folder
    else:
        candidates = [
            path
            for path in folder.rglob("VIDEO_TS")
            if path.is_dir()
        ]

        if not candidates:
            return None

        candidate = sorted(candidates, key=lambda item: len(item.parts))[0]

    if not (candidate / "VIDEO_TS.IFO").is_file():
        return None

    if not any(candidate.glob("VTS_*_1.VOB")):
        return None

    return candidate


def recognize_movie(folder_name: str, profiles: list[dict[str, Any]]) -> dict[str, Any] | None:
    for profile in profiles:
        if not profile.get("enabled", True):
            continue

        for pattern in profile.get("folder_patterns", []):
            if re.search(pattern, folder_name):
                return profile

    return None


def discover_pipeline_arguments(script: Path) -> set[str]:
    """Read argparse option strings without executing the movie pipeline."""

    try:
        tree = ast.parse(script.read_text(encoding="utf-8"))
    except Exception:
        return set()

    arguments: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        function = node.func
        if not isinstance(function, ast.Attribute):
            continue

        if function.attr != "add_argument":
            continue

        for argument in node.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                arguments.add(argument.value)

    return arguments


def add_supported_option(
    command: list[str],
    supported: set[str],
    options: tuple[str, ...],
    value: str | int | Path | None,
) -> bool:
    if value is None:
        return False

    for option in options:
        if option in supported:
            command.extend([option, str(value)])
            return True

    return False


def build_command(
    source: Path,
    profile: dict[str, Any],
    defaults: dict[str, Any],
) -> list[str]:
    supported = discover_pipeline_arguments(MOVIE_PIPELINE)

    command = [sys.executable, "-u", str(MOVIE_PIPELINE)]

    source_added = add_supported_option(
        command,
        supported,
        ("--device", "--source", "--input", "--dvd", "--path", "--video-ts"),
        source,
    )

    add_supported_option(
        command,
        supported,
        ("--title", "--movie-title", "--name"),
        profile["title"],
    )

    add_supported_option(
        command,
        supported,
        ("--year",),
        profile.get("year"),
    )

    add_supported_option(
        command,
        supported,
        ("--category",),
        profile.get("category", defaults.get("category", "General")),
    )

    add_supported_option(
        command,
        supported,
        ("--rating",),
        profile.get("rating", defaults.get("rating", "Unrated")),
    )

    add_supported_option(
        command,
        supported,
        ("--destination-root", "--movies-root", "--library"),
        profile.get(
            "destination_root",
            defaults.get("destination_root", "/mnt/media/Movies"),
        ),
    )

    if not source_added:
        # The existing script may use one positional source argument.
        positional_names = {
            argument
            for argument in supported
            if not argument.startswith("-")
        }

        if positional_names:
            command.append(str(source))
        else:
            raise RuntimeError(
                "Could not determine how jarvis_movie_dvd_ingest.py accepts "
                "its source path. Run it with --help and review its arguments."
            )

    return command


def destination_candidates(
    profile: dict[str, Any],
    defaults: dict[str, Any],
) -> list[Path]:
    root = Path(
        profile.get(
            "destination_root",
            defaults.get("destination_root", "/mnt/media/Movies"),
        )
    )

    title = profile["title"]
    year = profile.get("year")

    names = [title]
    if year:
        names.insert(0, f"{title} ({year})")

    candidates: list[Path] = []

    for name in names:
        candidates.extend(
            [
                root / name / f"{name}.mkv",
                root
                / profile.get("category", defaults.get("category", "General"))
                / profile.get("rating", defaults.get("rating", "Unrated"))
                / name
                / f"{name}.mkv",
            ]
        )

    return candidates


def write_failure(
    folder: Path,
    profile: dict[str, Any],
    reason: str,
    return_code: int | None = None,
) -> None:
    QUARANTINE_ROOT.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    safe_title = re.sub(r"[^A-Za-z0-9._-]+", "_", profile["title"]).strip("_")

    report = {
        "schema_version": 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "status": "BLOCKED",
        "source": str(folder),
        "title": profile["title"],
        "year": profile.get("year"),
        "reason": reason,
        "return_code": return_code,
        "source_preserved": True,
    }

    save_json(
        QUARANTINE_ROOT / f"{safe_title}-{stamp}.json",
        report,
    )


def main() -> int:
    print("=" * 72)
    print("JARVIS CALEB MOVIE QUEUE WORKER")
    print("=" * 72)

    for directory in (STATE_ROOT, REPORT_ROOT, QUARANTINE_ROOT):
        directory.mkdir(parents=True, exist_ok=True)

    if not SOURCE_ROOT.is_dir():
        log(f"BLOCK: Caleb source root is missing: {SOURCE_ROOT}")
        return 1

    if not PROFILE_FILE.is_file():
        log(f"BLOCK: Movie profile file is missing: {PROFILE_FILE}")
        return 1

    if not MOVIE_PIPELINE.is_file():
        log(f"BLOCK: Existing movie pipeline is missing: {MOVIE_PIPELINE}")
        return 1

    configuration = load_json(PROFILE_FILE, {})
    defaults = configuration.get("defaults", {})
    profiles = configuration.get("movies", [])

    registry = load_json(REGISTRY_FILE, {"version": 1, "processed": {}})
    processed = registry.setdefault("processed", {})

    passed = 0
    skipped = 0
    unknown = 0
    blocked = 0

    for folder in sorted(SOURCE_ROOT.iterdir()):
        if not folder.is_dir():
            continue

        if folder.name.endswith(".receiving"):
            continue

        profile = recognize_movie(folder.name, profiles)
        if profile is None:
            continue

        print()
        print("-" * 72)
        log(f"Movie source: {folder}")
        log(f"Movie title:  {profile['title']}")

        key = source_key(folder)

        if processed.get(key, {}).get("status") in {
            "IMPORTED",
            "ALREADY_IMPORTED",
        }:
            log("SKIP: Source is already recorded as imported.")
            skipped += 1
            continue

        video_ts = find_video_ts(folder)
        if video_ts is None:
            reason = "Complete VIDEO_TS structure was not found"
            log(f"BLOCK: {reason}")
            write_failure(folder, profile, reason)
            blocked += 1
            continue

        existing = [
            path
            for path in destination_candidates(profile, defaults)
            if path.is_file()
        ]

        if existing:
            log(f"SKIP: Destination movie already exists: {existing[0]}")

            processed[key] = {
                "status": "ALREADY_IMPORTED",
                "source": str(folder),
                "video_ts": str(video_ts),
                "title": profile["title"],
                "year": profile.get("year"),
                "destination": str(existing[0]),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "source_preserved": True,
            }

            save_json(REGISTRY_FILE, registry)
            skipped += 1
            continue

        try:
            command = build_command(video_ts, profile, defaults)
        except Exception as exc:
            reason = str(exc)
            log(f"BLOCK: {reason}")
            write_failure(folder, profile, reason)
            blocked += 1
            continue

        log("Starting existing Jarvis movie pipeline.")
        log("$ " + " ".join(repr(part) for part in command))

        result = subprocess.run(
            command,
            input="YES\n",
            text=True,
            check=False,
        )

        if result.returncode != 0:
            reason = f"Movie pipeline returned code {result.returncode}"
            log(f"BLOCK: {reason}")
            write_failure(
                folder,
                profile,
                reason,
                return_code=result.returncode,
            )
            blocked += 1
            continue

        created = [
            path
            for path in destination_candidates(profile, defaults)
            if path.is_file()
        ]

        if not created:
            # Search under the movie root in case the old pipeline's naming
            # differs slightly from the expected profile format.
            destination_root = Path(
                profile.get(
                    "destination_root",
                    defaults.get("destination_root", "/mnt/media/Movies"),
                )
            )

            normalized_title = profile["title"].lower()

            if destination_root.exists():
                created = [
                    path
                    for path in destination_root.rglob("*.mkv")
                    if normalized_title in path.stem.lower()
                ]

        if not created:
            reason = (
                "Movie pipeline exited successfully, but no matching "
                "destination MKV was found"
            )
            log(f"BLOCK: {reason}")
            write_failure(folder, profile, reason)
            blocked += 1
            continue

        destination = sorted(created, key=lambda path: path.stat().st_mtime)[-1]

        processed[key] = {
            "status": "IMPORTED",
            "source": str(folder),
            "video_ts": str(video_ts),
            "title": profile["title"],
            "year": profile.get("year"),
            "destination": str(destination),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "source_preserved": True,
        }

        save_json(REGISTRY_FILE, registry)

        log(f"PASS: Movie imported to {destination}")
        passed += 1

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "skipped": skipped,
        "unknown": unknown,
        "blocked": blocked,
        "registry": str(REGISTRY_FILE),
    }

    summary_path = (
        REPORT_ROOT
        / f"run-summary-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    )
    save_json(summary_path, summary)

    print()
    print("=" * 72)
    print("CALEB MOVIE SUMMARY")
    print("=" * 72)
    print(f"Passed:  {passed}")
    print(f"Skipped: {skipped}")
    print(f"Blocked: {blocked}")
    print(f"Summary: {summary_path}")

    return 0 if blocked == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
