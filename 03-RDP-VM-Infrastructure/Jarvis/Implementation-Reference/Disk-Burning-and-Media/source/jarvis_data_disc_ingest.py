#!/usr/bin/env python3

import argparse
import datetime
import json
import re
import subprocess
from pathlib import Path


CONFIG_PATH = Path.home() / "rdp-scripts/Jarvis/media/jarvis_media_config.json"


def load_config():
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def run_cmd(cmd, check=False):
    print(f"\n$ {' '.join(str(x) for x in cmd)}")
    result = subprocess.run(
        cmd,
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
    return name or "Unknown_Data_Disc"


def main():
    cfg = load_config()

    parser = argparse.ArgumentParser(description="Jarvis data disc ingest.")
    parser.add_argument("--device", default=cfg.get("device", "/dev/sr0"))
    parser.add_argument("--mountpoint", default="/mnt/disc")
    parser.add_argument("--destination-root", default=str(Path(cfg.get("archive_root", "/mnt/media/Archive")) / "Data_Discs"))
    parser.add_argument("--name", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    label_out, _ = run_cmd(["lsblk", "-no", "LABEL", args.device], check=False)
    label = safe_name(args.name or label_out.strip() or "Data_Disc")
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    destination = Path(args.destination_root) / f"{label}_{stamp}"
    mountpoint = Path(args.mountpoint)

    print("===== JARVIS DATA DISC INGEST =====")
    print(f"Label: {label}")
    print(f"Destination: {destination}")

    if args.dry_run:
        print("DRY RUN: no copy.")
        return

    confirm = input("Proceed with data disc copy/archive? Type YES: ")
    if confirm != "YES":
        print("Cancelled.")
        return

    mountpoint.mkdir(parents=True, exist_ok=True)

    run_cmd(["sudo", "mount", "-o", "ro", args.device, str(mountpoint)], check=True)

    destination.mkdir(parents=True, exist_ok=True)

    try:
        run_cmd(["rsync", "-avh", "--progress", str(mountpoint) + "/", str(destination) + "/"], check=True)
    finally:
        run_cmd(["sudo", "umount", str(mountpoint)], check=False)

    print("===== DATA DISC ARCHIVED =====")
    print(destination)


if __name__ == "__main__":
    main()
