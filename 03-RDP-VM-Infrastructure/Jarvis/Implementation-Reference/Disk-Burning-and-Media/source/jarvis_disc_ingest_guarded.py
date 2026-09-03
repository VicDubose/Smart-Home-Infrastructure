#!/usr/bin/env python3

import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path


REGISTRY_PATH = Path.home() / "rips/reports/jarvis_disc_registry.json"


def run_cmd(cmd, check=False):
    print(f"\n$ {' '.join(cmd)}")
    result = subprocess.run(cmd, text=True, encoding='utf-8', errors='replace', stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print(result.stdout)
    if check and result.returncode != 0:
        raise SystemExit(result.returncode)
    return result.stdout, result.returncode


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


def load_registry():
    if not REGISTRY_PATH.exists():
        return {}
    try:
        return json.loads(REGISTRY_PATH.read_text())
    except Exception:
        return {}


def save_registry(registry):
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2))


def make_fingerprint(show, season, label, titles):
    raw = {
        "show": show,
        "season": season,
        "label": label,
        "titles": [{"title": t.get("title"), "chapters": t.get("chapters")} for t in titles],
    }
    encoded = json.dumps(raw, sort_keys=True)
    return hashlib.sha256(encoded.encode()).hexdigest()[:16]


def main():
    parser = argparse.ArgumentParser(description="Jarvis guarded one-command DVD ingest.")
    parser.add_argument("--show", required=True)
    parser.add_argument("--season", required=True, type=int)
    parser.add_argument("--disc", required=True, type=int)
    parser.add_argument("--library", required=True)
    parser.add_argument("--ai", default="llama3:8b")
    parser.add_argument("--device", default="/dev/sr0")
    parser.add_argument("--staging", default=str(Path.home() / "rips/staging"))
    parser.add_argument("--allow-extra-candidates", action="store_true", help="Override guard when disc has more episode-looking titles than missing episodes.")
    args = parser.parse_args()

    show = args.show
    season = args.season
    library = Path(args.library)
    show_dir = library / show
    season_dir = show_dir / f"Season {season:02d}"
    staging = Path(args.staging)

    print("===== JARVIS GUARDED DISC INGEST =====")
    print(f"Show: {show}")
    print(f"Season: {season:02d}")
    print(f"Disc argument: {args.disc}")
    print(f"Library: {library}")
    print(f"AI reviewer: {args.ai}")
    print("")

    tv_show = find_show(show)
    season_eps = get_episodes(tv_show["id"], season)
    official_count = len(season_eps)

    existing = scan_existing(season_dir, season)
    missing = [i for i in range(1, official_count + 1) if i not in existing]

    print("===== LOCAL LIBRARY STATE =====")
    print(f"Official episode count: {official_count}")
    print(f"Existing: {', '.join(f'S{season:02d}E{x:02d}' for x in existing) if existing else 'none'}")
    print(f"Missing: {', '.join(f'S{season:02d}E{x:02d}' for x in missing) if missing else 'none'}")
    print("")

    if not missing:
        print("✅ Season is already complete. No rip needed.")
        return

    disc_info, _ = run_cmd(["dvdbackup", "-I", "-i", args.device])
    label_match = re.search(r'DVD with title "([^"]+)"', disc_info)
    label = label_match.group(1) if label_match else "not detected"

    titles = parse_dvdbackup_info(disc_info)
    play_all, candidates, extras = classify_titles(titles)
    fingerprint = make_fingerprint(show, season, label, titles)

    print("===== DISC SCAN =====")
    print(f"Disc label: {label}")
    print(f"Disc fingerprint: {fingerprint}")
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

    print("")

    registry = load_registry()
    prior = registry.get(fingerprint)

    if prior:
        prior_eps = prior.get("episodes", [])
        print("===== DUPLICATE DISC CHECK =====")
        print("⚠️ This disc fingerprint has been seen before.")
        print(f"Previously mapped episodes: {', '.join(prior_eps)}")

        all_prior_exist = True
        for ep_code in prior_eps:
            if not list(season_dir.glob(f"*{ep_code}*.mkv")):
                all_prior_exist = False

        if all_prior_exist:
            print("✅ All previously mapped episodes already exist in Jellyfin.")
            print("No rip needed. Duplicate disc blocked.")
            return
        else:
            print("Some prior mapped episodes are missing, continuing cautiously.")
        print("")

    if not candidates:
        print("ERROR: No episode candidates found. Stopping.")
        raise SystemExit(1)

    # Major out-of-order protection:
    # If there are more episode-looking titles than missing episodes remaining,
    # this is likely the wrong disc or an earlier duplicate disc.
    if len(candidates) > len(missing) and not args.allow_extra_candidates:
        print("===== SAFETY BLOCK =====")
        print("🚫 This disc has more episode-looking titles than episodes missing.")
        print(f"Episode-looking titles found: {len(candidates)}")
        print(f"Missing episodes remaining: {len(missing)}")
        print("")
        print("This usually means one of these is true:")
        print("- wrong disc inserted")
        print("- duplicate/out-of-order disc inserted")
        print("- disc contains episode-looking bonus material")
        print("")
        print("No rip was started. No files were moved.")
        print("Use --allow-extra-candidates only if you manually confirm the mapping is correct.")
        raise SystemExit(1)

    episode_numbers = missing[:len(candidates)]
    candidates = candidates[:len(episode_numbers)]

    print("===== PROPOSED RIP MAP =====")
    proposed_codes = []
    duplicate_destinations = []

    for title, ep_num in zip(candidates, episode_numbers):
        ep_code = f"S{season:02d}E{ep_num:02d}"
        proposed_codes.append(ep_code)
        ep_name = next((ep.get("name") for ep in season_eps if ep.get("number") == ep_num), "")
        dest = season_dir / f"{show} - {ep_code}.mkv"

        if dest.exists():
            duplicate_destinations.append(ep_code)
            action = "SKIP_DUPLICATE_DEST_EXISTS"
        else:
            action = "RIP"

        print(f"Title {title['title']} -> {ep_code} - {ep_name} [{action}]")

    if duplicate_destinations and len(duplicate_destinations) == len(proposed_codes):
        print("")
        print("✅ All proposed destinations already exist. No rip needed.")
        return

    if duplicate_destinations:
        print("")
        print("===== SAFETY BLOCK =====")
        print("🚫 Some proposed episode files already exist.")
        print(f"Duplicates: {', '.join(duplicate_destinations)}")
        print("No rip was started. No files were moved.")
        raise SystemExit(1)

    print("")
    confirm = input("Proceed with guarded rip/validate/move? Type YES: ")
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

    result = json.loads(validation_file.read_text())
    if result.get("final_result") != "PASS":
        print("🚫 Validation did not pass. Move blocked.")
        raise SystemExit(1)

    print("")
    print("===== MOVE ONLY IF VALID =====")
    run_cmd([
        "python3",
        str(Path.home() / "rdp-scripts/Jarvis/media/jarvis_move_if_valid.py"),
        "--validation", str(validation_file),
        "--destination", str(season_dir),
    ], check=True)

    registry[fingerprint] = {
        "show": show,
        "season": season,
        "disc_arg": args.disc,
        "disc_label": label,
        "episodes": proposed_codes,
        "title_map": [
            {"title": title["title"], "episode": ep_code}
            for title, ep_code in zip(candidates, proposed_codes)
        ],
    }
    save_registry(registry)

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
