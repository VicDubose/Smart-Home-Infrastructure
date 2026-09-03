
import sys
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
    return name or "Unknown Movie"


def detect_dvd_title(device):
    output, _ = run_cmd(["dvdbackup", "-I", "-i", device], check=False)
    match = re.search(r'DVD with title "([^"]+)"', output)
    if match:
        return safe_name(match.group(1).title())
    return "Unknown Movie"


def scan_title(device, title_num):
    output, _ = run_cmd(["HandBrakeCLI", "-i", device, "-t", str(title_num), "--scan"], check=False)
    match = re.search(r"\+ duration:\s+(\d+):(\d+):(\d+)", output)
    chapters = re.findall(r"\+ \d+: duration", output)

    if not match:
        return None

    h, m, s = map(int, match.groups())
    seconds = h * 3600 + m * 60 + s

    return {
        "title": title_num,
        "duration_seconds": seconds,
        "duration_human": f"{h:02d}:{m:02d}:{s:02d}",
        "chapters": len(chapters)
    }


def ffprobe_file(file_path):
    output, _ = run_cmd([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,size",
        "-of", "json",
        str(file_path)
    ], check=False)

    try:
        data = json.loads(output)
        fmt = data.get("format", {})
        return float(fmt.get("duration", 0)), int(fmt.get("size", 0))
    except Exception:
        return None, None


def human(seconds):
    if seconds is None:
        return "UNKNOWN"
    return f"{int(seconds // 60)}m {int(seconds % 60)}s"


def main():
    cfg = load_config()

    parser = argparse.ArgumentParser(description="Jarvis movie DVD ingest.")
    parser.add_argument("--device", default=cfg.get("device", "/dev/sr0"))
    parser.add_argument("--title", default=None)
    parser.add_argument("--category", default=cfg.get("default_movie_category", "General"))
    parser.add_argument("--rating", default=cfg.get("default_movie_rating", "Unrated"))
    parser.add_argument("--year", default=None)
    parser.add_argument("--ai", default=None)
    parser.add_argument("--staging", default=cfg.get("staging_root", str(Path.home() / "rips/staging")))
    parser.add_argument("--destination-root", default=cfg.get("movies_root", "/mnt/media/Movies"))
    parser.add_argument("--max-title", type=int, default=35)
    parser.add_argument("--title-number", type=int, default=None, help="Manually force DVD title number")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    raw_title = args.title if args.title else detect_dvd_title(args.device)
    movie_title = safe_name(raw_title)

    if args.year and f"({args.year})" not in movie_title:
        movie_title = f"{movie_title} ({args.year})"

    staging = Path(args.staging)
    dest_root = Path(args.destination_root)

    print("===== JARVIS MOVIE DVD INGEST =====")
    print(f"Movie title: {movie_title}")
    print(f"Category: {args.category}")
    print(f"Rating: {args.rating}")
    print("")

    scanned = []

    for t in range(1, args.max_title + 1):
        info = scan_title(args.device, t)
        if info:
            scanned.append(info)

    if not scanned:
        print("ERROR: no valid titles found.")
        raise SystemExit(1)

    print("===== TITLE SUMMARY =====")
    for item in scanned:
        print(f"Title {item['title']}: {item['duration_human']} ({item['chapters']} chapters)")

    if args.title_number is not None:
        forced = [x for x in scanned if x["title"] == args.title_number]
        if forced:
            main_title = forced[0]
        else:
            print(f"ERROR: forced title {args.title_number} was not found or could not be scanned.")
            raise SystemExit(1)
    else:
        movie_candidates = [x for x in scanned if x["duration_seconds"] >= 45 * 60]

        if not movie_candidates:
            print("ERROR: no movie-length title found.")
            raise SystemExit(1)

        main_title = max(movie_candidates, key=lambda x: x["duration_seconds"])

    print("")
    print("===== SELECTED MAIN TITLE =====")
    print(f"Title {main_title['title']} - {main_title['duration_human']}")

    output_file = staging / f"{movie_title}.mkv"
    dest_dir = dest_root / args.category / args.rating / movie_title
    dest_file = dest_dir / f"{movie_title}.mkv"

    print(f"Destination: {dest_file}")

    if args.dry_run:
        print("DRY RUN: no rip or move.")
        return

    if sys.stdin.isatty():
        confirm = input("Proceed with movie rip/move? Type YES: ")
    else:
        confirm = "YES"
        print("Automatic approval enabled for non-interactive ingest.")
    if confirm != "YES":
        print("Cancelled.")
        return

    staging.mkdir(parents=True, exist_ok=True)
    for f in staging.glob("*"):
        if f.is_file():
            f.unlink()

    run_cmd([
        "HandBrakeCLI",
        "-i", args.device,
        "-t", str(main_title["title"]),
        "-o", str(output_file),
        "--format", "av_mkv",
        "-e", "x264",
        "-q", "19",
        "-B", "160"
    ], check=True)

    duration, size = ffprobe_file(output_file)

    print("===== VALIDATION =====")
    print(f"Duration: {human(duration)}")
    print(f"Size: {size}")

    if duration is None or duration < 45 * 60:
        print("MOVE BLOCKED: movie runtime missing or too short.")
        raise SystemExit(1)

    if dest_file.exists():
        print(f"MOVE BLOCKED: destination already exists: {dest_file}")
        raise SystemExit(1)

    dest_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(output_file), str(dest_file))

    print("===== MOVED =====")
    print(dest_file)


if __name__ == "__main__":
    main()
