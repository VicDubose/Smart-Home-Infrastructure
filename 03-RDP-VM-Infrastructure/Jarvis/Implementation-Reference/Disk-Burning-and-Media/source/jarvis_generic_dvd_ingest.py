#!/usr/bin/env python3

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path


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
    return name or "Unknown DVD"


def detect_dvd_title(device):
    output, _ = run_cmd(["dvdbackup", "-I", "-i", device], check=False)
    match = re.search(r'DVD with title "([^"]+)"', output)
    if match:
        return safe_name(match.group(1))
    return "Unknown DVD"


def scan_title(device, title_num):
    output, _ = run_cmd(
        ["HandBrakeCLI", "-i", device, "-t", str(title_num), "--scan"],
        check=False,
    )

    duration_match = re.search(r"\+ duration:\s+(\d+):(\d+):(\d+)", output)
    chapter_matches = re.findall(r"\+ \d+: duration", output)

    if not duration_match:
        return None

    h = int(duration_match.group(1))
    m = int(duration_match.group(2))
    s = int(duration_match.group(3))
    seconds = h * 3600 + m * 60 + s

    return {
        "title": title_num,
        "duration_seconds": seconds,
        "duration_human": f"{h:02d}:{m:02d}:{s:02d}",
        "chapters": len(chapter_matches),
    }


def ffprobe_file(file_path):
    output, _ = run_cmd([
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration,size",
        "-of", "json",
        str(file_path),
    ], check=False)

    try:
        data = json.loads(output)
        fmt = data.get("format", {})
        return {
            "duration_seconds": float(fmt.get("duration", 0)),
            "size_bytes": int(fmt.get("size", 0)),
        }
    except Exception:
        return {
            "duration_seconds": None,
            "size_bytes": None,
        }


def human_time(seconds):
    if seconds is None:
        return "UNKNOWN"
    return f"{int(seconds // 60)}m {int(seconds % 60)}s"


def main():
    parser = argparse.ArgumentParser(description="Jarvis generic DVD/music-video ingest.")
    parser.add_argument("--device", default="/dev/sr0")
    parser.add_argument("--ai", default=None, help="Reserved for future AI review")
    parser.add_argument("--staging", default=str(Path.home() / "rips/staging"))
    parser.add_argument("--destination-root", default="/mnt/media/Music Videos")
    parser.add_argument("--name", default=None, help="Override folder/title name")
    parser.add_argument("--max-title", type=int, default=35)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    device = args.device
    staging = Path(args.staging)
    destination_root = Path(args.destination_root)

    dvd_title = safe_name(args.name) if args.name else detect_dvd_title(device)

    print("===== JARVIS GENERIC DVD INGEST =====")
    print(f"Device: {device}")
    print(f"Detected title: {dvd_title}")
    print(f"Destination root: {destination_root}")
    print("")

    print("===== SCANNING TITLES =====")
    scanned = []

    for title_num in range(1, args.max_title + 1):
        info = scan_title(device, title_num)
        if info:
            scanned.append(info)

    if not scanned:
        print("ERROR: No valid DVD titles found.")
        raise SystemExit(1)

    print("")
    print("===== TITLE SUMMARY =====")
    for item in scanned:
        print(
            f"Title {item['title']}: "
            f"{item['duration_human']} "
            f"({item['chapters']} chapters)"
        )

    # Music video heuristic:
    # Keep short/medium individual titles between 2 and 20 minutes.
    # Drop a combined/play-all title if its duration is roughly the sum of the smaller titles.
    individual_candidates = [
        item for item in scanned
        if 2 * 60 <= item["duration_seconds"] <= 20 * 60
    ]

    if not individual_candidates:
        print("")
        print("No short individual music-video style titles found.")
        print("This may be a movie/concert DVD. Manual generic movie lane needed.")
        raise SystemExit(1)

    total_individual = sum(item["duration_seconds"] for item in individual_candidates)

    play_all_titles = []
    for item in scanned:
        if item in individual_candidates:
            continue
        if abs(item["duration_seconds"] - total_individual) <= 90:
            play_all_titles.append(item)

    # If a title is much longer and equals sum of shorts, treat it as play-all.
    # For Michael Jackson: Title 5 = ~28:36, sum of Titles 1-4 ≈ same.
    final_titles = individual_candidates

    print("")
    print("===== CLASSIFICATION =====")
    print("Individual video titles:")
    for item in final_titles:
        print(f"  KEEP Title {item['title']} - {item['duration_human']}")

    if play_all_titles:
        print("Detected play-all/combined titles:")
        for item in play_all_titles:
            print(f"  SKIP Title {item['title']} - {item['duration_human']}")

    destination = destination_root / dvd_title

    print("")
    print(f"Destination folder: {destination}")

    if args.dry_run:
        print("")
        print("DRY RUN: No files ripped or moved.")
        return

    confirm = input("Proceed with generic DVD rip/move? Type YES: ")
    if confirm != "YES":
        print("Cancelled.")
        return

    staging.mkdir(parents=True, exist_ok=True)
    for file in staging.glob("*"):
        if file.is_file():
            file.unlink()

    print("")
    print("===== RIPPING INDIVIDUAL VIDEOS =====")

    ripped_files = []

    for idx, item in enumerate(final_titles, start=1):
        out_file = staging / f"{dvd_title} - Video {idx:02d}.mkv"
        run_cmd([
            "HandBrakeCLI",
            "-i", device,
            "-t", str(item["title"]),
            "-o", str(out_file),
            "--format", "av_mkv",
            "-e", "x264",
            "-q", "19",
            "-B", "160",
        ], check=True)
        ripped_files.append(out_file)

    print("")
    print("===== VALIDATING RIPPED FILES =====")

    all_good = True
    for file in ripped_files:
        probe = ffprobe_file(file)
        duration = probe["duration_seconds"]
        size = probe["size_bytes"]

        print(f"{file.name}: duration={human_time(duration)}, size={size}")

        if duration is None or duration < 2 * 60:
            print(f"  REVIEW: runtime is missing or too short")
            all_good = False

        if size is None or size < 10 * 1024 * 1024:
            print(f"  REVIEW: file is too small")
            all_good = False

    if not all_good:
        print("")
        print("MOVE BLOCKED: One or more files failed validation.")
        raise SystemExit(1)

    destination.mkdir(parents=True, exist_ok=True)

    print("")
    print("===== MOVING TO MUSIC VIDEOS =====")

    for file in ripped_files:
        dest = destination / file.name
        if dest.exists():
            print(f"Duplicate exists, skipping: {dest}")
            continue

        print(f"Moving {file} -> {dest}")
        shutil.move(str(file), str(dest))

    print("")
    print("===== FINAL FOLDER =====")
    for file in sorted(destination.glob("*.mkv")):
        print(file.name)


if __name__ == "__main__":
    main()
