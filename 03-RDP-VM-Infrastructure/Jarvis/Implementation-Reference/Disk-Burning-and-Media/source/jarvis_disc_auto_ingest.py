#!/usr/bin/env python3

import argparse
import json
import os
import re
import subprocess
from pathlib import Path


CONFIG_PATH = Path.home() / "rdp-scripts/Jarvis/media/jarvis_media_config.json"
LOCK_PATH = Path("/tmp/jarvis_media_ingest.lock")


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


def acquire_lock():
    try:
        fd = os.open(str(LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
    except FileExistsError:
        print(f"Another Jarvis media ingest appears to be running: {LOCK_PATH}")
        print("If this is stale, remove it with:")
        print(f"  rm -f {LOCK_PATH}")
        raise SystemExit(1)


def release_lock():
    try:
        LOCK_PATH.unlink()
    except FileNotFoundError:
        pass


def detect_disc(device):
    info = {
        "disc_type": "unknown",
        "fstype": None,
        "label": None,
        "dvd_title": None
    }

    lsblk_out, _ = run_cmd(["lsblk", "-J", "-o", "NAME,SIZE,TYPE,FSTYPE,LABEL,MODEL,TRAN", device], check=False)

    try:
        data = json.loads(lsblk_out)
        dev = data["blockdevices"][0]
        info["fstype"] = dev.get("fstype")
        info["label"] = dev.get("label")
    except Exception:
        pass

    dvd_out, _ = run_cmd(["dvdbackup", "-I", "-i", device], check=False)

    if "DVD-Video information" in dvd_out or "VIDEO_TS" in dvd_out:
        info["disc_type"] = "dvd_video"
        m = re.search(r'DVD with title "([^"]+)"', dvd_out)
        if m:
            info["dvd_title"] = m.group(1)
        return info

    cd_out, cd_code = run_cmd(["cd-discid", device], check=False)

    if cd_code == 0 and cd_out.strip():
        info["disc_type"] = "audio_cd"
        return info

    if info["fstype"] in ["udf", "iso9660"]:
        info["disc_type"] = "data_disc"
        return info

    return info


def scan_dvd_titles(device, max_title=35):
    titles = []

    for t in range(1, max_title + 1):
        out, _ = run_cmd(["HandBrakeCLI", "-i", device, "-t", str(t), "--scan"], check=False)
        m = re.search(r"\+ duration:\s+(\d+):(\d+):(\d+)", out)

        if not m:
            continue

        h, mi, s = map(int, m.groups())
        seconds = h * 3600 + mi * 60 + s
        titles.append({"title": t, "seconds": seconds, "human": f"{h:02d}:{mi:02d}:{s:02d}"})

    return titles


def classify_generic_dvd(titles):
    long_titles = [t for t in titles if t["seconds"] >= 45 * 60]
    short_titles = [t for t in titles if 2 * 60 <= t["seconds"] <= 20 * 60]

    if long_titles:
        return "movie"

    if len(short_titles) >= 2:
        return "music_video"

    return "unknown"


def main():
    cfg = load_config()

    parser = argparse.ArgumentParser(description="Jarvis master disc auto-ingest.")
    parser.add_argument("--device", default=cfg.get("device", "/dev/sr0"))
    parser.add_argument("--ai", required=True)
    parser.add_argument("--show", default=None)
    parser.add_argument("--season", type=int, default=None)
    parser.add_argument("--disc", type=int, default=None)
    parser.add_argument("--title", default=None)
    parser.add_argument("--category", default=cfg.get("default_movie_category", "General"))
    parser.add_argument("--rating", default=cfg.get("default_movie_rating", "Unrated"))
    parser.add_argument("--year", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    acquire_lock()

    try:
        print("===== JARVIS MASTER DISC AUTO-INGEST =====")

        info = detect_disc(args.device)

        print("===== DETECTION RESULT =====")
        print(json.dumps(info, indent=2))

        if info["disc_type"] == "dvd_video":
            if args.show and args.season and args.disc:
                print("Routing to TV DVD pipeline.")
                cmd = [
                    "python3",
                    str(Path.home() / "rdp-scripts/Jarvis/media/jarvis_disc_ingest_guarded_v2.py"),
                    "--device", args.device,
                    "--show", args.show,
                    "--season", str(args.season),
                    "--disc", str(args.disc),
                    "--ai", args.ai
                ]
                if args.dry_run:
                    print("Dry-run not supported by TV pipeline here. Use TV script directly for dry-run.")
                    return
                subprocess.run(cmd)
                return

            print("Generic DVD detected. Inspecting titles...")
            titles = scan_dvd_titles(args.device)

            print("===== GENERIC DVD TITLE SUMMARY =====")
            for t in titles:
                print(f"Title {t['title']}: {t['human']}")

            dvd_class = classify_generic_dvd(titles)

            print(f"Classification: {dvd_class}")

            if dvd_class == "movie":
                cmd = [
                    "python3",
                    str(Path.home() / "rdp-scripts/Jarvis/media/jarvis_movie_dvd_ingest.py"),
                    "--device", args.device,
                    "--ai", args.ai,
                    "--category", args.category,
                    "--rating", args.rating
                ]

                if args.title:
                    cmd += ["--title", args.title]
                if args.year:
                    cmd += ["--year", args.year]
                if args.dry_run:
                    cmd += ["--dry-run"]

                subprocess.run(cmd)
                return

            if dvd_class == "music_video":
                cmd = [
                    "python3",
                    str(Path.home() / "rdp-scripts/Jarvis/media/jarvis_generic_dvd_ingest.py"),
                    "--device", args.device,
                ]

                if args.dry_run:
                    cmd += ["--dry-run"]

                subprocess.run(cmd)
                return

            print("BLOCKED: generic DVD classification unknown.")
            return

        if info["disc_type"] == "audio_cd":
            print("Routing to Audio CD pipeline.")
            cmd = [
                "python3",
                str(Path.home() / "rdp-scripts/Jarvis/media/jarvis_cd_ingest.py"),
                "--device", args.device,
            ]
            if args.dry_run:
                cmd += ["--dry-run"]
            subprocess.run(cmd)
            return

        if info["disc_type"] == "data_disc":
            print("Routing to Data Disc pipeline.")
            cmd = [
                "python3",
                str(Path.home() / "rdp-scripts/Jarvis/media/jarvis_data_disc_ingest.py"),
                "--device", args.device,
            ]
            if args.dry_run:
                cmd += ["--dry-run"]
            subprocess.run(cmd)
            return

        print("BLOCKED: unknown disc type.")

    finally:
        release_lock()


if __name__ == "__main__":
    main()
