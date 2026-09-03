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


def run_cmd(cmd):
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        return result.stdout
    except Exception as e:
        return f"ERROR running {' '.join(cmd)}: {e}"


def safe_name(name):
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")


def tvmaze_get_json(url):
    with urllib.request.urlopen(url, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def find_tvmaze_show(show_name):
    query = urllib.parse.quote(show_name)
    url = f"https://api.tvmaze.com/search/shows?q={query}"
    results = tvmaze_get_json(url)

    if not results:
        return None

    # Pick the highest score result.
    best = results[0]["show"]
    return best


def get_tvmaze_episodes(show_id):
    url = f"https://api.tvmaze.com/shows/{show_id}/episodes"
    return tvmaze_get_json(url)


def get_season_episodes(episodes, season):
    return [ep for ep in episodes if ep.get("season") == season]


def scan_existing_episodes(season_dir, season):
    existing = []
    pattern = re.compile(rf"S{season:02d}E(\d{{2}})", re.IGNORECASE)

    if not season_dir.exists():
        return existing

    for file in season_dir.rglob("*"):
        if file.is_file():
            match = pattern.search(file.name)
            if match:
                existing.append(int(match.group(1)))

    return sorted(set(existing))


def parse_dvdbackup_info(text):
    """
    Parse dvdbackup -I output.
    It gives title numbers and chapter counts, but not clean durations.
    We use chapter count as a rough signal:
    - Title 1 with many chapters is often Play All
    - Titles with 9-13 chapters are often episodes
    """
    titles = []
    current_title = None

    for line in text.splitlines():
        title_match = re.search(r"Title\s+(\d+):", line)
        if title_match:
            current_title = {
                "title": int(title_match.group(1)),
                "chapters": None,
                "audio_channels": None,
            }
            titles.append(current_title)
            continue

        chapter_match = re.search(r"Title\s+\d+\s+has\s+(\d+)\s+chapters", line)
        if chapter_match and current_title:
            current_title["chapters"] = int(chapter_match.group(1))
            continue

        audio_match = re.search(r"Title\s+\d+\s+has\s+(\d+)\s+audio channels", line)
        if audio_match and current_title:
            current_title["audio_channels"] = int(audio_match.group(1))
            continue

    return titles


def classify_titles(titles):
    likely_episodes = []
    likely_play_all = []
    likely_extras = []

    for t in titles:
        n = t["title"]
        chapters = t.get("chapters")

        if chapters is None:
            likely_extras.append(t)
        elif chapters >= 30:
            likely_play_all.append(t)
        elif 8 <= chapters <= 14:
            likely_episodes.append(t)
        else:
            likely_extras.append(t)

    return likely_play_all, likely_episodes, likely_extras


def create_plan_script(
    plan_path,
    show,
    season,
    disc,
    likely_episodes,
    episode_numbers,
    staging_dir,
    season_dir,
):
    lines = [
        "#!/usr/bin/env bash",
        "set -e",
        "",
        f'echo "===== JARVIS MEDIA PLAN: {show} Season {season:02d} Disc {disc} ====="',
        f'mkdir -p "{staging_dir}"',
        f'rm -rf "{staging_dir}"/*',
        "",
        'echo "Starting HandBrake rip to staging..."',
        "",
    ]

    for title, ep_num in zip(likely_episodes, episode_numbers):
        title_num = title["title"]
        output_file = f"{show} - S{season:02d}E{ep_num:02d}.mkv"
        output_path = f"{staging_dir}/{output_file}"

        lines.append(
            f'HandBrakeCLI -i /dev/sr0 -t {title_num} '
            f'-o "{output_path}" --format av_mkv -e x264 -q 19 -B 160'
        )

    lines.extend([
        "",
        'echo ""',
        'echo "Rip complete. Files in staging:"',
        f'ls -lh "{staging_dir}"',
        "",
        f'mkdir -p "{season_dir}"',
        "",
        'echo ""',
        'echo "Moving finished files to Jellyfin HDD..."',
    ])

    for ep_num in episode_numbers:
        file_name = f"{show} - S{season:02d}E{ep_num:02d}.mkv"
        lines.append(f'mv "{staging_dir}/{file_name}" "{season_dir}/{file_name}"')

    lines.extend([
        "",
        'echo ""',
        f'echo "===== {show} Season {season:02d} Disc {disc} COMPLETE ====="',
        f'ls -lh "{season_dir}"',
        "",
    ])

    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text("\n".join(lines))
    os.chmod(plan_path, 0o755)


def main():
    parser = argparse.ArgumentParser(
        description="Jarvis media disc verification and safe rename/rip planner."
    )
    parser.add_argument("--show", required=True, help="Show name, example: The Originals")
    parser.add_argument("--season", required=True, type=int, help="Season number")
    parser.add_argument("--disc", required=True, type=int, help="Disc number")
    parser.add_argument("--library", required=True, help="Library root, example: /mnt/media/Shows")
    parser.add_argument("--staging", default=str(Path.home() / "rips/staging"))
    parser.add_argument("--device", default="/dev/sr0")
    args = parser.parse_args()

    show = args.show
    season = args.season
    disc = args.disc
    library = Path(args.library)
    staging_dir = Path(args.staging)

    show_dir = library / show
    season_dir = show_dir / f"Season {season:02d}"

    print("===== JARVIS DISC VERIFY =====")
    print(f"Show: {show}")
    print(f"Season: {season:02d}")
    print(f"Disc: {disc}")
    print(f"Library: {library}")
    print(f"Season folder: {season_dir}")
    print("")

    # TVMaze metadata
    try:
        tv_show = find_tvmaze_show(show)
        if not tv_show:
            print("ERROR: Could not find show in TVMaze.")
            sys.exit(1)

        episodes = get_tvmaze_episodes(tv_show["id"])
        season_eps = get_season_episodes(episodes, season)

        official_count = len(season_eps)
        print("===== OFFICIAL METADATA =====")
        print(f"TVMaze match: {tv_show.get('name')} ({tv_show.get('premiered')})")
        print(f"Official Season {season:02d} episode count: {official_count}")
        print("")

        if official_count:
            print("Episode list:")
            for ep in season_eps:
                print(f"  S{season:02d}E{ep['number']:02d} - {ep.get('name')}")
            print("")

    except Exception as e:
        print(f"WARNING: Could not pull TVMaze metadata: {e}")
        official_count = None
        season_eps = []

    # Existing library state
    existing = scan_existing_episodes(season_dir, season)
    highest_existing = max(existing) if existing else 0
    next_episode = highest_existing + 1

    print("===== LOCAL LIBRARY STATE =====")
    if existing:
        print(f"Existing episodes found: {', '.join(f'S{season:02d}E{x:02d}' for x in existing)}")
        print(f"Highest existing episode: S{season:02d}E{highest_existing:02d}")
        print(f"Expected next episode: S{season:02d}E{next_episode:02d}")
    else:
        print("No existing episodes found for this season.")
        print(f"Expected next episode: S{season:02d}E01")
    print("")

    if official_count:
        missing = [i for i in range(1, official_count + 1) if i not in existing]
        print(f"Missing before this disc: {', '.join(f'S{season:02d}E{x:02d}' for x in missing)}")
        print("")

    # Disc scan
    print("===== DISC SCAN =====")
    print(f"Running: dvdbackup -I -i {args.device}")
    disc_info = run_cmd(["dvdbackup", "-I", "-i", args.device])

    title_match = re.search(r'DVD with title "([^"]+)"', disc_info)
    if title_match:
        print(f"Disc label: {title_match.group(1)}")
    else:
        print("Disc label: not detected")

    titles = parse_dvdbackup_info(disc_info)
    play_all, likely_episodes, extras = classify_titles(titles)

    print("")
    print("Likely Play All titles:")
    for t in play_all:
        print(f"  Title {t['title']} - {t.get('chapters')} chapters")

    print("")
    print("Likely episode titles:")
    for t in likely_episodes:
        print(f"  Title {t['title']} - {t.get('chapters')} chapters")

    print("")
    print("Likely extras/shorts:")
    for t in extras:
        print(f"  Title {t['title']} - {t.get('chapters')} chapters")
    print("")

    if not likely_episodes:
        print("ERROR: No likely episode titles found. Do not generate a rip plan yet.")
        sys.exit(1)

    # Proposed mapping
    episode_numbers = list(range(next_episode, next_episode + len(likely_episodes)))

    if official_count:
        episode_numbers = [ep for ep in episode_numbers if ep <= official_count]
        likely_episodes = likely_episodes[:len(episode_numbers)]

    print("===== PROPOSED MAPPING =====")
    for title, ep_num in zip(likely_episodes, episode_numbers):
        ep_name = ""
        for ep in season_eps:
            if ep.get("number") == ep_num:
                ep_name = f" - {ep.get('name')}"
                break
        print(f"Title {title['title']} → S{season:02d}E{ep_num:02d}{ep_name}")

    if official_count:
        after_this = set(existing) | set(episode_numbers)
        missing_after = [i for i in range(1, official_count + 1) if i not in after_this]
        print("")
        if missing_after:
            print(f"Missing after this disc would be: {', '.join(f'S{season:02d}E{x:02d}' for x in missing_after)}")
        else:
            print("Missing after this disc would be: none")

    print("")

    # Plan script
    plan_name = f"{safe_name(show)}_S{season:02d}_Disc{disc:02d}_plan.sh"
    plan_path = Path.home() / "rips/plans" / plan_name

    create_plan_script(
        plan_path=plan_path,
        show=show,
        season=season,
        disc=disc,
        likely_episodes=likely_episodes,
        episode_numbers=episode_numbers,
        staging_dir=str(staging_dir),
        season_dir=str(season_dir),
    )

    print("===== SAFE PLAN CREATED =====")
    print(f"Plan script:")
    print(f"  {plan_path}")
    print("")
    print("Review it with:")
    print(f"  cat \"{plan_path}\"")
    print("")
    print("Run it only after review:")
    print(f"  bash \"{plan_path}\"")
    print("")
    print("No files were ripped, moved, or renamed by this verifier.")


if __name__ == "__main__":
    main()
