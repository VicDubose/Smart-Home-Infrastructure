#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

RAW_ROOT = Path("/mnt/appdata/arm/media/raw")
LOG_ROOT = Path("/mnt/appdata/arm/logs")
HOLD_ROOT = Path("/mnt/appdata/arm/media/failed-hold")

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".m4v"}

FAILURE_MARKERS = (
    "Call to MakeMKV failed",
    "Error while running MakeMKV",
    "A fatal error has occurred and ARM is exiting",
    "Failed to save title",
)

MARKER_NAME = ".jarvis-failed-hold.json"
MINIMUM_IDLE_SECONDS = 15 * 60


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def arm_is_active() -> tuple[bool, str]:
    command = [
        "docker",
        "exec",
        "arm",
        "bash",
        "-lc",
        (
            "pgrep -af "
            "'[/]opt/arm/arm/ripper/main.py|"
            "[H]andBrakeCLI|[m]akemkvcon|[d]vdbackup|[f]fmpeg'"
        ),
    ]

    process = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )

    output = (process.stdout or "").strip()

    if process.returncode == 0 and output:
        return True, output

    if process.returncode == 1 and not output:
        return False, ""

    return True, (
        "Unable to prove ARM is idle; supervisor will block.\n"
        f"{output}"
    )


def media_files(path: Optional[Path]) -> list[Path]:
    if path is None or not path.is_dir():
        return []

    return [
        item
        for item in path.rglob("*")
        if item.is_file()
        and item.suffix.casefold() in VIDEO_EXTENSIONS
    ]


def newest_activity(path: Path) -> float:
    timestamps = [path.stat().st_mtime]

    for item in path.rglob("*"):
        try:
            timestamps.append(item.stat().st_mtime)
        except FileNotFoundError:
            continue

    return max(timestamps)


def read_matching_log(raw_directory: Path) -> tuple[Optional[Path], str]:
    exact_needles = (
        f"/home/arm/media/raw/{raw_directory.name}",
        f"/mnt/appdata/arm/media/raw/{raw_directory.name}",
    )

    matches: list[tuple[float, Path, str]] = []

    if not LOG_ROOT.is_dir():
        return None, ""

    for log_path in LOG_ROOT.glob("*.log"):
        try:
            text = log_path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except OSError:
            continue

        if not any(needle in text for needle in exact_needles):
            continue

        matches.append(
            (
                log_path.stat().st_mtime,
                log_path,
                text,
            )
        )

    if not matches:
        return None, ""

    matches.sort(key=lambda item: item[0])
    _, log_path, text = matches[-1]

    return log_path, text


def completed_path_from_log(text: str) -> Optional[Path]:
    matches = re.findall(
        r'Final Output directory "'
        r'(/home/arm/media/completed/[^"]+)"',
        text,
    )

    if not matches:
        return None

    host_path = matches[-1].replace(
        "/home/arm/media/",
        "/mnt/appdata/arm/media/",
        1,
    )

    return Path(host_path)


def transcode_path_for(completed_path: Optional[Path]) -> Optional[Path]:
    if completed_path is None:
        return None

    value = str(completed_path)

    if "/media/completed/" not in value:
        return None

    return Path(
        value.replace(
            "/media/completed/",
            "/media/transcode/",
            1,
        )
    )


def failure_reason(text: str) -> Optional[str]:
    present = [
        marker
        for marker in FAILURE_MARKERS
        if marker in text
    ]

    if not present:
        return None

    return "; ".join(present)


def remove_if_empty(path: Optional[Path]) -> None:
    if path is None or not path.is_dir():
        return

    try:
        path.rmdir()
        print(f"REMOVED_EMPTY={path}")
    except OSError:
        pass


def hold_failed_directory(
    raw_directory: Path,
    log_path: Path,
    reason: str,
    completed_path: Optional[Path],
    hold_hours: float,
    commit: bool,
) -> None:
    age_seconds = max(
        0,
        time.time() - newest_activity(raw_directory),
    )

    age_hours = age_seconds / 3600

    if age_seconds < MINIMUM_IDLE_SECONDS:
        print(
            f"WAIT_RECENT age={age_hours:.2f}h "
            f"path={raw_directory}"
        )
        return

    raw_videos = media_files(raw_directory)
    completed_videos = media_files(completed_path)

    if completed_videos:
        print(
            f"SKIP_COMPLETED videos={len(completed_videos)} "
            f"path={completed_path}"
        )
        return

    print(
        f"FAILED_CONFIRMED age={age_hours:.2f}h "
        f"videos={len(raw_videos)} "
        f"path={raw_directory}"
    )
    print(f"  log={log_path}")
    print(f"  reason={reason}")

    if not commit:
        print("  action=WOULD_MOVE_TO_24_HOUR_HOLD")
        return

    HOLD_ROOT.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().astimezone().strftime(
        "%Y%m%d-%H%M%S"
    )
    destination = HOLD_ROOT / (
        f"{stamp}--{raw_directory.name}"
    )

    if destination.exists():
        raise RuntimeError(
            f"Hold destination already exists: {destination}"
        )

    os.rename(raw_directory, destination)

    held_epoch = time.time()
    purge_epoch = held_epoch + (hold_hours * 3600)

    marker = {
        "version": 1,
        "state": "failed_hold",
        "original_path": str(raw_directory),
        "hold_path": str(destination),
        "arm_log": str(log_path),
        "failure_reason": reason,
        "raw_video_count": len(raw_videos),
        "completed_path": (
            str(completed_path)
            if completed_path is not None
            else None
        ),
        "held_at": now_text(),
        "held_epoch": held_epoch,
        "purge_after_epoch": purge_epoch,
        "hold_hours": hold_hours,
    }

    marker_path = destination / MARKER_NAME
    marker_path.write_text(
        json.dumps(marker, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"HELD={destination}")
    print(
        "PURGE_AFTER="
        + datetime.fromtimestamp(
            purge_epoch
        ).astimezone().isoformat(timespec="seconds")
    )

    remove_if_empty(completed_path)
    remove_if_empty(
        transcode_path_for(completed_path)
    )


def purge_expired(commit: bool) -> None:
    if not HOLD_ROOT.is_dir():
        return

    current = time.time()

    for directory in sorted(HOLD_ROOT.iterdir()):
        if not directory.is_dir():
            continue

        marker_path = directory / MARKER_NAME

        if not marker_path.is_file():
            print(
                f"PROTECTED_UNMARKED_HOLD={directory}"
            )
            continue

        try:
            marker = json.loads(
                marker_path.read_text(encoding="utf-8")
            )
            purge_after = float(
                marker["purge_after_epoch"]
            )
        except (
            OSError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            print(
                f"PROTECTED_INVALID_MARKER "
                f"path={directory} error={error}"
            )
            continue

        remaining = purge_after - current

        if remaining > 0:
            print(
                f"HOLD_ACTIVE remaining="
                f"{remaining / 3600:.2f}h "
                f"path={directory}"
            )
            continue

        if not commit:
            print(
                f"WOULD_PURGE_EXPIRED={directory}"
            )
            continue

        shutil.rmtree(directory)
        print(f"PURGED_EXPIRED={directory}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Hold confirmed failed ARM raw jobs for a "
            "fixed period, then safely purge them."
        )
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Perform moves and eligible purges.",
    )
    parser.add_argument(
        "--hold-hours",
        type=float,
        default=24,
        help="Retention period before deletion.",
    )

    args = parser.parse_args()

    if args.hold_hours < 1:
        print("BLOCK: Hold period must be at least 1 hour.")
        return 2

    active, detail = arm_is_active()

    if active:
        print("WAIT: ARM activity or status uncertainty detected.")
        if detail:
            print(detail)
        return 0

    print("ARM_STATUS=IDLE")
    print(
        "MODE="
        + ("COMMIT" if args.commit else "DRY_RUN")
    )
    print(f"HOLD_HOURS={args.hold_hours:g}")

    if not RAW_ROOT.is_dir():
        print(f"BLOCK: ARM raw root is missing: {RAW_ROOT}")
        return 2

    for raw_directory in sorted(
        RAW_ROOT.iterdir(),
        key=lambda item: item.name.casefold(),
    ):
        if not raw_directory.is_dir():
            continue

        log_path, log_text = read_matching_log(
            raw_directory
        )

        if log_path is None:
            print(
                f"PROTECTED_NO_MATCHING_LOG={raw_directory}"
            )
            continue

        reason = failure_reason(log_text)

        if reason is None:
            print(
                f"PROTECTED_NO_FATAL_MARKER={raw_directory}"
            )
            continue

        completed_path = completed_path_from_log(
            log_text
        )

        hold_failed_directory(
            raw_directory=raw_directory,
            log_path=log_path,
            reason=reason,
            completed_path=completed_path,
            hold_hours=args.hold_hours,
            commit=args.commit,
        )

    purge_expired(commit=args.commit)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
