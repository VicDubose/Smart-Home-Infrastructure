#!/usr/bin/env python3

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path


DEFAULT_DEVICE = "/dev/sr0"
DEFAULT_QUEUE = Path("/mnt/appdata/jarvis-intake/incoming/local-dvd")


def run(command):
    return subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def slugify(value):
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "unknown"


def detect_video_dvd(device):
    result = run(["dvdbackup", "-I", "-i", device])
    output = result.stdout or ""

    detected_title = None
    match = re.search(r'DVD with title "([^"]+)"', output)

    if match:
        detected_title = match.group(1).strip()

    return {
        "detected": result.returncode == 0 or "DVD-Video information" in output,
        "disc_label": detected_title,
        "probe_returncode": result.returncode,
        "probe_excerpt": output[-3000:],
    }


def derive_profile(args):
    if args.show:
        return "tv-short" if args.profile == "auto" else args.profile

    if args.title:
        return "movie" if args.profile == "auto" else args.profile

    raise SystemExit("BLOCK: Supply either --show or --title.")


def validate_arguments(args):
    if args.show and args.title:
        raise SystemExit("BLOCK: A job cannot be both TV and movie.")

    if args.show:
        if args.season is None:
            raise SystemExit("BLOCK: TV jobs require --season.")
        if args.disc is None:
            raise SystemExit("BLOCK: TV jobs require --disc.")
        if args.count is None:
            raise SystemExit("BLOCK: TV jobs require --count.")

    if args.title and args.count is None:
        args.count = 1


def main():
    parser = argparse.ArgumentParser(
        description="Create one normalized Jarvis local-DVD job."
    )

    parser.add_argument("--device", default=DEFAULT_DEVICE)

    parser.add_argument("--show")
    parser.add_argument("--season", type=int)
    parser.add_argument("--disc", type=int)

    parser.add_argument("--title")
    parser.add_argument("--year", type=int)
    parser.add_argument("--category", default="General")
    parser.add_argument("--rating", default="Unrated")

    parser.add_argument("--count", type=int)
    parser.add_argument("--start", type=int, default=1)

    parser.add_argument("--ai", default="llama3:8b")

    parser.add_argument(
        "--profile",
        default="auto",
        choices=[
            "auto",
            "movie",
            "tv-short",
            "tv-standard",
            "music-video",
            "audio",
            "data-disc",
            "raw-archive",
        ],
    )

    parser.add_argument(
        "--queue",
        default=str(DEFAULT_QUEUE),
    )

    parser.add_argument("--dry-run", action="store_true")


    parser.add_argument(
        "--type",
        dest="media_type_alias",
        choices=[
            "movie",
            "movie-collection",
            "tv-short",
            "tv-standard",
            "music-video",
            "audio",
            "data-disc",
            "raw-archive",
        ],
        default=None,
        help="Friendly media-type alias for --profile",
    )

    args = parser.parse_args()

    if args.media_type_alias:
        if args.profile != "auto" and args.profile != args.media_type_alias:
            parser.error("--type and --profile disagree")
        args.profile = args.media_type_alias

    validate_arguments(args)

    device = Path(args.device)

    if not device.exists():
        raise SystemExit(f"BLOCK: Device does not exist: {device}")

    print("===== DETECT LOCAL DVD =====")
    print(f"Device: {device}")

    dvd = detect_video_dvd(str(device))

    if not dvd["detected"]:
        print(dvd["probe_excerpt"])
        raise SystemExit(
            f"BLOCK: No readable DVD-Video disc was detected in {device}."
        )

    print(f"Disc label: {dvd['disc_label'] or 'unknown'}")
    print("PASS: DVD-Video detected.")

    profile = derive_profile(args)
    media_type = "tv" if args.show else "movie"

    supplied_name = args.show or args.title
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    short_id = uuid.uuid4().hex[:10]

    job_id = f"{slugify(supplied_name)}-{timestamp}-{short_id}"

    queue_root = Path(args.queue)
    job_root = queue_root / job_id

    source_metadata = {
        "lane": "local_dvd",
        "device": str(device),
        "disc_label": dvd["disc_label"],
        "filesystem": "DVD_VIDEO",
        "intake_method": "optical",
    }

    manifest = {
        "manifest_version": 1,
        "job_id": job_id,
        "created_at": datetime.now().astimezone().isoformat(),
        "state": "ready",
        "priority": 50,

        "source": "local_dvd",
        "media_type": media_type,
        "profile": profile,

        "title": args.title,
        "year": args.year,
        "category": args.category if args.title else None,
        "rating": args.rating if args.title else None,

        "show": args.show,
        "season": args.season,
        "disc": args.disc,

        "episode_start": args.start if args.show else None,
        "expected_items": args.count,

        "ai_model": args.ai,

        "source_metadata": source_metadata,

        "source_path": str(device),
        "staging_path": str(
            Path("/mnt/appdata/jarvis-burner-staging/local-dvd") / job_id
        ),

        "destination_root": (
            "/mnt/media/Shows"
            if media_type == "tv"
            else "/mnt/media/Movies"
        ),

        "workflow": {
            "intake": "pending",
            "rip": "pending",
            "cooldown_after_rip": "pending",
            "technical_validation": "pending",
            "ai_validation": "pending",
            "library_move": "pending",
            "cleanup": "pending",
        },

        "attempts": {
            "rip": 0,
            "validation": 0,
            "move": 0,
        },

        "errors": [],
    }

    print("")
    print("===== NORMALIZED JOB =====")
    print(json.dumps(manifest, indent=2))

    if args.dry_run:
        print("")
        print("DRY RUN: Manifest was not queued.")
        return

    job_root.mkdir(parents=True, exist_ok=False)

    manifest_path = job_root / "job.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    status_path = job_root / "status.txt"
    status_path.write_text(
        "READY: waiting for local DVD worker\n",
        encoding="utf-8",
    )

    print("")
    print("============================================================")
    print(" JARVIS DVD JOB QUEUED")
    print("============================================================")
    print(f"Job ID:   {job_id}")
    print(f"Manifest: {manifest_path}")
    print(f"Status:   {status_path}")


if __name__ == "__main__":
    main()
