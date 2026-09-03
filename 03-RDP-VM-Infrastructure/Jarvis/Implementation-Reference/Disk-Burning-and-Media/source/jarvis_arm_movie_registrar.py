#!/usr/bin/env python3
"""
Register newly completed ARM movie files into Jarvis's local-bluray lane.

First normal run:
    Existing files are recorded as a baseline and are not queued.

Future runs:
    New stable movie files are copied into the local-bluray burner lane
    with a ready job.json manifest.

Optional:
    --backfill queues existing files that have not previously been registered.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jarvis_job import atomic_write, normalize_manifest


ARM_COMPLETED = Path("/mnt/appdata/arm/media/completed")
STAGE_ROOT = Path("/mnt/appdata/jarvis-burner-staging/local-bluray")
STATE_FILE = Path.home() / "Jarvis/state/arm-movie-registrar.json"
REPORT_ROOT = Path.home() / "Jarvis/reports/arm-movie-registrar"

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".m4v"}
IGNORED_PARTS = {"tv", "music", "audio", "quarantine"}

MINIMUM_AGE_SECONDS = 600
DEFAULT_PRIORITY = 100


def now() -> datetime:
    return datetime.now(timezone.utc)


def now_text() -> str:
    return now().isoformat(timespec="seconds")


def stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def atomic_json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def normalize_title(value: str) -> str:
    value = value.replace("_", " ")
    value = re.sub(r"\s+", " ", value).strip()

    value = re.sub(
        r"[_ -]20\d{6}[_ -]\d{6}$",
        "",
        value,
    ).strip()

    return value or "Unknown Movie"


def title_and_year(path: Path) -> tuple[str, int | None]:
    """
    Derive movie title and year from the MKV filename.

    Prefer the filename because ARM parent folders may contain disc labels,
    serial numbers, or generic names. Fall back to the parent directory only
    when the filename itself is generic.
    """

    generic_names = {
        "movie",
        "main",
        "mainfeature",
        "main_feature",
        "feature",
        "title",
        "video",
    }

    stem = path.stem.strip()

    normalized_stem = re.sub(
        r"[^a-z0-9]+",
        "",
        stem.casefold(),
    )

    looks_generic = (
        normalized_stem in generic_names
        or re.fullmatch(r"title\d+", normalized_stem) is not None
        or re.fullmatch(r"[a-z]\d+t\d+", normalized_stem) is not None
        or re.fullmatch(r"t\d+", normalized_stem) is not None
    )

    candidate = (
        path.parent.name.strip()
        if looks_generic
        else stem
    )

    # Remove common ARM/disc suffixes while preserving the real title.
    candidate = re.sub(
        r"(?i)[\s._-]+(?:disc|disk|d)\s*\d+\s*$",
        "",
        candidate,
    ).strip()

    year_match = re.search(
        r"(?<!\d)\((19\d{2}|20\d{2})\)\s*$",
        candidate,
    )

    if year_match is None:
        year_match = re.search(
            r"(?<!\d)(19\d{2}|20\d{2})\s*$",
            candidate,
        )

    year = int(year_match.group(1)) if year_match else None

    if year_match:
        title = candidate[:year_match.start()].strip(" ._-()[]")
    else:
        title = candidate.strip(" ._-()[]")

    title = re.sub(r"[_]+", " ", title)
    title = re.sub(r"\s{2,}", " ", title).strip()

    if not title:
        title = path.stem.strip() or "Unknown Movie"

    return title, year


def source_key(path: Path) -> str:
    stat = path.stat()
    raw = (
        f"{path.resolve()}|"
        f"{stat.st_size}|"
        f"{stat.st_mtime_ns}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def job_id(path: Path, title: str, year: int | None) -> str:
    identity = source_key(path)[:16]
    display = f"{title} ({year})" if year else title

    safe = re.sub(
        r"[^A-Za-z0-9()' -]+",
        "",
        display,
    ).strip()

    safe = re.sub(r"\s+", " ", safe)

    return f"{safe}-{identity}"


def discover_movies() -> list[Path]:
    discovered: list[Path] = []

    if not ARM_COMPLETED.is_dir():
        return discovered

    for path in ARM_COMPLETED.rglob("*"):
        if not path.is_file():
            continue

        if path.suffix.casefold() not in VIDEO_EXTENSIONS:
            continue

        relative_parts = {
            part.casefold()
            for part in path.relative_to(ARM_COMPLETED).parts
        }

        if relative_parts & IGNORED_PARTS:
            continue

        discovered.append(path)

    return sorted(
        discovered,
        key=lambda item: (
            item.stat().st_mtime,
            str(item).casefold(),
        ),
    )


def stable(path: Path) -> tuple[bool, int]:
    age = max(
        0,
        int(time.time() - path.stat().st_mtime),
    )

    return age >= MINIMUM_AGE_SECONDS, age


def register(path: Path) -> dict[str, Any]:
    title, year = title_and_year(path)
    identifier = job_id(path, title, year)

    job_root = STAGE_ROOT / identifier
    display = f"{title} ({year})" if year else title
    movie_root = job_root / display
    manifest_path = job_root / "job.json"

    if manifest_path.is_file():
        return {
            "status": "already_staged",
            "source": str(path),
            "job": str(job_root),
        }

    job_root.mkdir(parents=True, exist_ok=False)
    movie_root.mkdir(parents=True, exist_ok=False)

    destination = movie_root / f"{display}{path.suffix.casefold()}"

    try:
        # Avoid physically duplicating large ARM movie files when
        # staging and source are on the same filesystem.
        #
        # Same filesystem: hardlink
        # Different filesystem / unsupported: normal copy
        try:
            if path.stat().st_dev == movie_root.stat().st_dev:
                os.link(path, destination)
            else:
                shutil.copy2(path, destination)
        except OSError:
            if destination.exists():
                destination.unlink()
            shutil.copy2(path, destination)

        if destination.stat().st_size != path.stat().st_size:
            raise RuntimeError(
                "Copied file size does not match source."
            )

        legacy_manifest = {
            "version": 1,
            "job_id": identifier,
            "job_type": "local-bluray",
            "media_type": "movie",
            "title": title,
            "year": year,
            "priority": DEFAULT_PRIORITY,
            "state": "ready",
            "registered_at": now_text(),
            "source_path": str(job_root),
            "media_path": str(destination),
            "raw_source_path": str(path),
            "raw_source_preserved": True,
            "worker": str(
                Path.home()
                / "rdp-scripts/Jarvis/media/"
                  "jarvis_movie_arm_router.py"
            ),
            "drive_role": "bluray",
        }

        manifest = normalize_manifest(legacy_manifest)
        manifest["expected_items"] = 1
        manifest["workflow"]["intake"] = "complete"
        manifest["workflow"]["rip"] = "complete"
        manifest["workflow"]["cooldown_after_rip"] = "complete"
        manifest["workflow"]["technical_validation"] = "ready"

        atomic_write(
            manifest_path,
            manifest,
        )

    except Exception:
        shutil.rmtree(
            job_root,
            ignore_errors=True,
        )
        raise

    return {
        "status": "registered",
        "source": str(path),
        "job": str(job_root),
        "manifest": str(manifest_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Queue old unregistered completed movies.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
    )
    args = parser.parse_args()

    STATE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    REPORT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    STAGE_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    state = load_json(
        STATE_FILE,
        {
            "version": 1,
            "initialized": False,
            "sources": {},
        },
    )

    sources = state.setdefault(
        "sources",
        {},
    )

    candidates = discover_movies()

    report: dict[str, Any] = {
        "started_at": now_text(),
        "mode": (
            "dry-run"
            if args.dry_run
            else "backfill"
            if args.backfill
            else "normal"
        ),
        "candidates": len(candidates),
        "registered": [],
        "baseline": [],
        "skipped": [],
        "errors": [],
    }

    first_run = not bool(
        state.get("initialized")
    )

    for source in candidates:
        try:
            key = source_key(source)
            is_stable, age = stable(source)

            if not is_stable:
                report["skipped"].append(
                    {
                        "source": str(source),
                        "reason": "not_stable",
                        "age_seconds": age,
                    }
                )
                continue

            prior = sources.get(key)

            if prior:
                report["skipped"].append(
                    {
                        "source": str(source),
                        "reason": prior.get(
                            "status",
                            "already_recorded",
                        ),
                    }
                )
                continue

            if first_run and not args.backfill:
                sources[key] = {
                    "status": "baseline",
                    "source": str(source),
                    "recorded_at": now_text(),
                }

                report["baseline"].append(
                    str(source)
                )
                continue

            if args.dry_run:
                report["registered"].append(
                    {
                        "status": "would_register",
                        "source": str(source),
                    }
                )
                continue

            result = register(source)
            report["registered"].append(result)

            sources[key] = {
                "status": result["status"],
                "source": str(source),
                "job": result.get("job"),
                "recorded_at": now_text(),
            }

        except Exception as error:
            report["errors"].append(
                {
                    "source": str(source),
                    "error": str(error),
                }
            )

    if not args.dry_run:
        state["initialized"] = True
        state["last_run_at"] = now_text()

        atomic_json_write(
            STATE_FILE,
            state,
        )

    report["finished_at"] = now_text()

    report_path = (
        REPORT_ROOT
        / f"registration-{stamp()}.json"
    )

    atomic_json_write(
        report_path,
        report,
    )

    print("=" * 72)
    print("JARVIS ARM MOVIE REGISTRAR")
    print("=" * 72)
    print(f"Candidates:  {report['candidates']}")
    print(f"Baseline:    {len(report['baseline'])}")
    print(f"Registered:  {len(report['registered'])}")
    print(f"Skipped:     {len(report['skipped'])}")
    print(f"Errors:      {len(report['errors'])}")
    print(f"Report:      {report_path}")

    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
