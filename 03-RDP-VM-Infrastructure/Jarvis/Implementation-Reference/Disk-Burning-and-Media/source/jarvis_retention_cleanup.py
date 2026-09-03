#!/usr/bin/env python3

import json
import os
import re
import shutil
import subprocess
import time

from datetime import datetime
from pathlib import Path


HOME = Path("/home/onsiteadmin")

RETENTION_DAYS = 7
RETENTION_SECONDS = RETENTION_DAYS * 86400

SAFE_MARKER = ".jarvis_safe_to_purge"

LOG = HOME / "Jarvis/logs/retention-cleanup.log"


# ============================================================
# MANAGED AREAS
# ============================================================

MANAGED_ROOTS = [
    Path("/mnt/appdata/jarvis-burner-staging/local-dvd-raw"),
    Path("/mnt/appdata/jarvis-burner-staging/local-dvd"),
    Path("/mnt/appdata/jarvis-burner-staging/local-bluray"),

    Path("/mnt/appdata/arm/media/raw"),
    Path("/mnt/appdata/arm/media/transcode"),
    Path("/mnt/appdata/arm/media/completed"),
    Path("/mnt/appdata/arm/media/personal-staging"),

    HOME / "Jarvis/jobs",
]


# ============================================================
# ABSOLUTE EXCLUSIONS
# ============================================================

EXCLUDED_ROOTS = [
    Path("/mnt/appdata/caleb-media"),
    Path("/mnt/appdata/arm/media/failed-hold"),
]


# Never automatically delete known mystery/quarantine items.
PRESERVE_NAMES = {
    "7000080254_1_20260814-075753",
}


# Any directory containing one of these is held indefinitely.
HOLD_MARKERS = {
    ".keep",
    ".jarvis_hold",
    ".no_purge",
}


# ============================================================
# LANDMAN AUTO-MARKING
# ============================================================

LANDMAN_RAW_ROOT = Path(
    "/mnt/appdata/jarvis-burner-staging/local-dvd-raw"
)

LANDMAN_JOB_ROOT = HOME / "Jarvis/jobs/landman"

LANDMAN_LIBRARY = Path(
    "/mnt/media/Shows/Landman"
)

LANDMAN_RAW_RE = re.compile(
    r"^LANDMAN_SEASON(?P<season>\d+)_DISC(?P<disc>\d+)_"
    r"\d{8}-\d{6}$"
)

LANDMAN_JOB_RE = re.compile(
    r"^S(?P<season>\d{2})D(?P<disc>\d{2})-\d{8}-\d{6}$"
)


def log(message):
    stamp = (
        datetime.now()
        .astimezone()
        .isoformat(timespec="seconds")
    )

    line = f"{stamp} {message}"

    print(line)

    LOG.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with LOG.open(
        "a",
        encoding="utf-8",
    ) as handle:
        handle.write(line + "\n")


def resolve(path):
    try:
        return path.resolve()
    except Exception:
        return path.absolute()


def inside(path, root):
    path = resolve(path)
    root = resolve(root)

    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def excluded(path):
    return any(
        inside(path, root)
        for root in EXCLUDED_ROOTS
    )


def managed(path):
    return any(
        inside(path, root)
        for root in MANAGED_ROOTS
    )


def process_lines():
    result = subprocess.run(
        ["ps", "-eo", "args="],
        capture_output=True,
        text=True,
        check=True,
    )

    return result.stdout.splitlines()


def active(path):
    needle = str(path)

    for line in process_lines():

        if "jarvis_retention_cleanup.py" in line:
            continue

        if needle in line:
            return True

    return False


def protected(path):
    if excluded(path):
        return True

    if path.name in PRESERVE_NAMES:
        return True

    if path.name.endswith(".receiving"):
        return True

    if path.is_symlink():
        return True

    if path.is_dir():
        for marker in HOLD_MARKERS:
            if (path / marker).exists():
                return True

    return False


def verify_media(path):
    if not path.is_file():
        return False

    try:
        if path.stat().st_size == 0:
            return False
    except OSError:
        return False

    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries",
            "stream=codec_type",
            "-of", "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return False

    streams = {
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    }

    return (
        "video" in streams
        and "audio" in streams
    )


def landman_episode_range(disc):
    mapping = {
        1: range(1, 4),
        2: range(4, 7),
        3: range(7, 11),
    }

    return mapping.get(disc)


def landman_final_file(season, episode):
    return (
        LANDMAN_LIBRARY
        / f"Season {season:02d}"
        / f"Landman - S{season:02d}E{episode:02d}.mkv"
    )


def landman_final_verified(season, disc):
    episodes = landman_episode_range(disc)

    if episodes is None:
        return False

    for episode in episodes:

        final = landman_final_file(
            season,
            episode,
        )

        if not verify_media(final):
            return False

    return True


def write_safe_marker(path, reason):
    marker = path / SAFE_MARKER

    if marker.exists():
        return

    payload = {
        "marked_at": (
            datetime.now()
            .astimezone()
            .isoformat()
        ),
        "retention_days": RETENTION_DAYS,
        "reason": reason,
    }

    marker.write_text(
        json.dumps(
            payload,
            indent=2,
        ),
        encoding="utf-8",
    )

    log(f"MARKED SAFE: {path}")


def auto_mark_landman_raws():
    root = LANDMAN_RAW_ROOT

    if not root.is_dir():
        return

    for path in root.iterdir():

        if not path.is_dir():
            continue

        if protected(path):
            continue

        match = LANDMAN_RAW_RE.match(
            path.name
        )

        if not match:
            continue

        season = int(
            match.group("season")
        )

        disc = int(
            match.group("disc")
        )

        if active(path):
            log(
                f"ACTIVE RAW — preserving: {path}"
            )
            continue

        if not (
            path / ".rip_complete"
        ).is_file():

            log(
                f"INCOMPLETE RAW — preserving: {path}"
            )
            continue

        if not landman_final_verified(
            season,
            disc,
        ):
            log(
                f"NOT IMPORTED — preserving: {path}"
            )
            continue

        write_safe_marker(
            path,
            (
                f"Landman S{season:02d}"
                f"D{disc:02d} final episodes "
                "verified in library"
            ),
        )


def auto_mark_landman_jobs():
    root = LANDMAN_JOB_ROOT

    if not root.is_dir():
        return

    for path in root.iterdir():

        if not path.is_dir():
            continue

        if protected(path):
            continue

        match = LANDMAN_JOB_RE.match(
            path.name
        )

        if not match:
            continue

        season = int(
            match.group("season")
        )

        disc = int(
            match.group("disc")
        )

        if active(path):
            log(
                f"ACTIVE JOB — preserving: {path}"
            )
            continue

        if not landman_final_verified(
            season,
            disc,
        ):
            continue

        write_safe_marker(
            path,
            (
                f"Landman S{season:02d}"
                f"D{disc:02d} final media verified; "
                "staging job no longer required"
            ),
        )


def safe_marker_candidates():
    candidates = set()

    for root in MANAGED_ROOTS:

        if not root.is_dir():
            continue

        if excluded(root):
            continue

        try:
            markers = root.rglob(
                SAFE_MARKER
            )
        except Exception as exc:
            log(
                f"SCAN ERROR {root}: {exc}"
            )
            continue

        for marker in markers:

            path = marker.parent

            if not managed(path):
                continue

            if excluded(path):
                continue

            if protected(path):
                continue

            candidates.add(path)

    return sorted(
        candidates,
        key=lambda p: len(p.parts),
    )


def already_covered(path, selected):
    for parent in selected:

        if parent == path:
            continue

        if inside(path, parent):
            return True

    return False


def directory_size(path):
    total = 0

    try:
        for item in path.rglob("*"):

            if item.is_symlink():
                continue

            if not item.is_file():
                continue

            try:
                total += item.stat().st_size
            except OSError:
                pass

    except OSError:
        pass

    return total


def purge():
    now = time.time()

    selected = []

    for path in safe_marker_candidates():

        if already_covered(
            path,
            selected,
        ):
            continue

        marker = path / SAFE_MARKER

        if not marker.is_file():
            continue

        if excluded(path):
            log(
                f"EXCLUDED — preserving: {path}"
            )
            continue

        if protected(path):
            log(
                f"PROTECTED — preserving: {path}"
            )
            continue

        if active(path):
            log(
                f"ACTIVE AT PURGE — preserving: {path}"
            )
            continue

        try:
            marker_age = (
                now
                - marker.stat().st_mtime
            )
        except OSError:
            continue

        if marker_age < RETENTION_SECONDS:

            remaining = (
                RETENTION_SECONDS
                - marker_age
            ) / 86400

            log(
                f"RETENTION {remaining:.1f}d remaining: "
                f"{path}"
            )

            selected.append(path)
            continue

        size = directory_size(path)

        try:
            shutil.rmtree(path)
        except Exception as exc:
            log(
                f"PURGE FAILED {path}: {exc}"
            )
            continue

        gib = size / (1024 ** 3)

        log(
            f"PURGED after {RETENTION_DAYS}d: "
            f"{path} ({gib:.2f} GiB)"
        )

        selected.append(path)


def report_configuration():
    log(
        f"RETENTION POLICY: {RETENTION_DAYS} days "
        "after SAFE marker"
    )

    for root in EXCLUDED_ROOTS:
        log(
            f"EXCLUDED ROOT: {root}"
        )


def main():
    log(
        "===== JARVIS RETENTION SWEEP ====="
    )

    report_configuration()

    auto_mark_landman_raws()
    auto_mark_landman_jobs()

    purge()

    log(
        "===== RETENTION SWEEP COMPLETE ====="
    )


main()
