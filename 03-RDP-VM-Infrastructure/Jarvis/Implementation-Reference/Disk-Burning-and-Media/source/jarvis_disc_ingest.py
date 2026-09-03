#!/usr/bin/env python3

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def run_cmd(cmd, check=False):
    print(f"\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(result.stdout)
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)
    return result.stdout


def tvmaze_json(url):
    with urllib.request.urlopen(url, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def find_show(show):
    url = f"https://api.tvmaze.com/search/shows?q={urllib.parse.quote(show)}"
    results = tvmaze_json(url)
    if not results:
        raise SystemExit(f"ERROR: Could not find show: {show}")
    return results[0]["show"]


def get_episodes(show_id, season):
    url = f"https://api.tvmaze.com/shows/{show_id}/episodes"
    episodes = tvmaze_json(url)
    return [ep for ep in episodes if ep.get("season") == season]


def scan_existing(season_dir, season):
    pattern = re.compile(rf"S{season:02d}E(\d{{2}})", re.IGNORECASE)
    found = []

    if not season_dir.exists():
        return found

    for file in season_dir.rglob("*"):
        if file.is_file():
            match = pattern.search(file.name)
            if match:
                found.append(int(match.group(1)))

    return sorted(set(found))


def parse_dvdbackup_info(text):
    titles = []
    current = None

    for line in text.splitlines():
        m = re.search(r"Title\s+(\d+):", line)
        if m:
            current = {"title": int(m.group(1)), "chapters": None}
            titles.append(current)
            continue

        c = re.search(r"Title\s+\d+\s+has\s+(\d+)\s+chapters", line)
        if c and current:
            current["chapters"] = int(c.group(1))

    return titles


def classify_titles(titles):
    play_all = []
    candidates = []
    extras = []

    for t in titles:
        chapters = t.get("chapters")
        if chapters is None:
            extras.append(t)
        elif chapters >= 30:
            play_all.append(t)
        elif 8 <= chapters <= 14:
            candidates.append(t)
        else:
            extras.append(t)

    return play_all, candidates, extras


def main():
    parser = argparse.ArgumentParser(description="Jarvis one-command DVD ingest.")
    parser.add_argument("--show", required=True)
    parser.add_argument("--season", required=True, type=int)
    parser.add_argument("--disc", required=True, type=int)
    parser.add_argument("--library", required=True)
    parser.add_argument("--ai", default="llama3:8b")
    parser.add_argument("--device", default="/dev/sr0")
    parser.add_argument("--staging", default=str(Path.home() / "rips/staging"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    show = args.show
    season = args.season
    library = Path(args.library)
    show_dir = library / show
    season_dir = show_dir / f"Season {season:02d}"
    staging = Path(args.staging)

    print("===== JARVIS DISC INGEST =====")
    print(f"Show: {show}")
    print(f"Season: {season:02d}")
    print(f"Disc: {args.disc}")
    print(f"Library: {library}")
    print(f"AI reviewer: {args.ai}")
    print("")

    tv_show = find_show(show)
    season_eps = get_episodes(tv_show["id"], season)
    official_count = len(season_eps)

    print("===== OFFICIAL METADATA =====")
    print(f"TVMaze match: {tv_show.get('name')} ({tv_show.get('premiered')})")
    print(f"Official episode count: {official_count}")
    print("")

    existing = scan_existing(season_dir, season)
    highest = max(existing) if existing else 0
    missing = [i for i in range(1, official_count + 1) if i not in existing]

    print("===== LOCAL LIBRARY STATE =====")
    print(f"Existing: {', '.join(f'S{season:02d}E{x:02d}' for x in existing) if existing else 'none'}")
    print(f"Missing: {', '.join(f'S{season:02d}E{x:02d}' for x in missing) if missing else 'none'}")
    print("")

    if not missing:
        print("Nothing missing for this season. No rip needed.")
        return

    disc_info = run_cmd(["dvdbackup", "-I", "-i", args.device])
    label = re.search(r'DVD with title "([^"]+)"', disc_info)
    print("===== DISC INFO =====")
    print(f"Disc label: {label.group(1) if label else 'not detected'}")

    titles = parse_dvdbackup_info(disc_info)
    play_all, candidates, extras = classify_titles(titles)

    print("")
    print("Likely Play All:")
    for t in play_all:
        print(f"  Title {t['title']} - {t.get('chapters')} chapters")

    print("Likely Episode Candidates:")
    for t in candidates:
        print(f"  Title {t['title']} - {t.get('chapters')} chapters")

    print("Likely Extras:")
    for t in extras:
        print(f"  Title {t['title']} - {t.get('chapters')} chapters")

    if not candidates:
        print("ERROR: No episode candidates found. Stopping.")
        raise SystemExit(1)

    # Map candidates to missing episodes only.
    episode_numbers = missing[:len(candidates)]
    candidates = candidates[:len(episode_numbers)]

    print("")
    print("===== PROPOSED RIP MAP =====")
    for title, ep_num in zip(candidates, episode_numbers):
        ep_name = next((ep.get("name") for ep in season_eps if ep.get("number") == ep_num), "")
        exists = (season_dir / f"{show} - S{season:02d}E{ep_num:02d}.mkv").exists()
        action = "SKIP_DUPLICATE" if exists else "RIP"
        print(f"Title {title['title']} -> S{season:02d}E{ep_num:02d} - {ep_name} [{action}]")

    if args.dry_run:
        print("")
        print("DRY RUN: no files were ripped or moved.")
        return

    print("")
    confirm = input("Proceed with rip/validate/move? Type YES: ")
    if confirm != "YES":
        print("Cancelled.")
        return

    staging.mkdir(parents=True, exist_ok=True)
    for f in staging.glob("*"):
        if f.is_file():
            f.unlink()

    print("")
    print("===== RIPPING TO STAGING =====")
    for title, ep_num in zip(candidates, episode_numbers):
        out = staging / f"{show} - S{season:02d}E{ep_num:02d}.mkv"
        run_cmd([
            "HandBrakeCLI",
            "-i", args.device,
            "-t", str(title["title"]),
            "-o", str(out),
            "--format", "av_mkv",
            "-e", "x264",
            "-q", "19",
            "-B", "160",
        ], check=True)

    validation_file = staging / "validation_result.json"

    print("")
    print("===== VALIDATING WITH JARVIS =====")
    run_cmd([
        "python3",
        str(Path.home() / "rdp-scripts/Jarvis/media/jarvis_validate_rip.py"),
        "--show", show,
        "--season", str(season),
        "--start", str(episode_numbers[0]),
        "--end", str(episode_numbers[-1]),
        "--staging", str(staging),
        "--write-result", str(validation_file),
        "--ai", args.ai,
    ], check=True)

    print("")
    print("===== MOVE ONLY IF VALID =====")
    run_cmd([
        "python3",
        str(Path.home() / "rdp-scripts/Jarvis/media/jarvis_move_if_valid.py"),
        "--validation", str(validation_file),
        "--destination", str(season_dir),
    ], check=True)

    print("")
    print("===== FINAL AUDIT =====")
    run_cmd([
        "python3",
        str(Path.home() / "rdp-scripts/Jarvis/media/jarvis_library_audit.py"),
        "--show", show,
        "--library", str(library),
    ], check=False)


if __name__ == "__main__":
    main()
