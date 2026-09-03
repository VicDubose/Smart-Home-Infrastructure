#!/usr/bin/env python3

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path


CONFIG_PATH = Path.home() / "rdp-scripts/Jarvis/media/jarvis_media_config.json"


def load_config():
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def run_cmd(cmd, cwd=None, check=False):
    print(f"\n$ {' '.join(str(x) for x in cmd)}")
    result = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    print(result.stdout)
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)
    return result.stdout, result.returncode


def safe_name(name):
    name = re.sub(r"[^\w\s\-.()&']", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name or "Unknown"


def main():
    cfg = load_config()

    parser = argparse.ArgumentParser(description="Jarvis audio CD ingest.")
    parser.add_argument("--device", default=cfg.get("device", "/dev/sr0"))
    parser.add_argument("--format", default="flac")
    parser.add_argument("--staging-root", default=str(Path.home() / "rips/music_staging"))
    parser.add_argument("--destination-root", default=cfg.get("music_root", "/mnt/media/Music"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    discid_out, code = run_cmd(["cd-discid", args.device], check=False)

    if code != 0 or not discid_out.strip():
        print("ERROR: not detected as an Audio CD.")
        raise SystemExit(1)

    disc_id = safe_name(discid_out.split()[0])
    staging = Path(args.staging_root) / disc_id
    destination = Path(args.destination_root) / "Albums" / "_Unsorted_Audio_CDs" / disc_id

    print("===== JARVIS AUDIO CD INGEST =====")
    print(f"Disc ID: {disc_id}")
    print(f"Staging: {staging}")
    print(f"Destination: {destination}")

    if args.dry_run:
        print("DRY RUN: no rip or move.")
        return

    confirm = input("Proceed with audio CD rip/move? Type YES: ")
    if confirm != "YES":
        print("Cancelled.")
        return

    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)

    run_cmd([
        "abcde",
        "-d", args.device,
        "-o", args.format,
        "-N"
    ], cwd=staging, check=True)

    files = list(staging.rglob(f"*.{args.format}"))

    if not files:
        print("MOVE BLOCKED: no ripped audio files found.")
        raise SystemExit(1)

    destination.mkdir(parents=True, exist_ok=True)

    for file in files:
        target = destination / file.name
        if target.exists():
            print(f"Skipping duplicate: {target}")
            continue
        shutil.move(str(file), str(target))

    print("===== MOVED AUDIO FILES =====")
    for file in sorted(destination.glob("*")):
        print(file)


if __name__ == "__main__":
    main()
