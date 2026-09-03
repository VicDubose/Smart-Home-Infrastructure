#!/usr/bin/env python3

import os
import argparse
import hashlib
import json
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path


REGISTRY_PATH = Path.home() / "rips/reports/jarvis_disc_registry.json"


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


def make_fingerprint(show, season, label, titles, device=None, disc=None):
    ifo_signature = []

    if device:
        video_ts = Path(device)

        if video_ts.is_dir():
            for ifo in sorted(video_ts.glob("*.IFO")):
                h = hashlib.sha256()

                with ifo.open("rb") as fh:
                    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                        h.update(chunk)

                ifo_signature.append({
                    "name": ifo.name,
                    "size": ifo.stat().st_size,
                    "sha256": h.hexdigest(),
                })

    raw = {
        "show": show,
        "season": season,
        "disc": disc,
        "label": label,
        "titles": [
            {
                "title": t.get("title"),
                "chapters": t.get("chapters"),
            }
            for t in titles
        ],
        "ifo_signature": ifo_signature,
    }

    encoded = json.dumps(raw, sort_keys=True)
    return hashlib.sha256(encoded.encode()).hexdigest()[:16]


def rip_title(device, title_num, output_file):
    if output_file.exists():
        output_file.unlink()

    run_cmd([
        "HandBrakeCLI",
        "-i", device,
        "-t", str(title_num),
        "-o", str(output_file),
        "--format", "av_mkv",
        "-e", "x264",
        "-q", "19",
        "-B", "160",
    ], check=True)


def run_validation(show, season, start_ep, end_ep, staging, validation_file, ai):
    run_cmd([
        "python3",
        str(Path.home() / "rdp-scripts/Jarvis/media/jarvis_validate_rip.py"),
        "--show", show,
        "--season", str(season),
        "--start", str(start_ep),
        "--end", str(end_ep),
        "--staging", str(staging),
        "--write-result", str(validation_file),
        "--ai", ai,
    ], check=True)

    if not validation_file.exists():
        raise SystemExit("ERROR: validation_result.json was not created.")

    return json.loads(validation_file.read_text())


def scan_title_duration_seconds(device, title_num):
    proc = subprocess.run(
        [
            "HandBrakeCLI",
            "-i", device,
            "-t", str(title_num),
            "--scan",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )

    output = proc.stdout or ""
    print(output)

    match = re.search(
        r"(?:scan: duration is|\+ duration:)\s+(\d+):(\d+):(\d+)",
        output,
    )
    if not match:
        return None

    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    return hours * 3600 + minutes * 60 + seconds


def human_duration(seconds):
    if seconds is None:
        return "UNKNOWN"
    return f"{seconds // 60}m {seconds % 60}s"


def main():
    parser = argparse.ArgumentParser(description="Jarvis guarded DVD ingest V2 with auto-rerip recovery.")
    parser.add_argument("--show", required=True)
    parser.add_argument("--season", required=True, type=int)
    parser.add_argument("--disc", required=True, type=int)
    parser.add_argument("--start", type=int, default=None, help="Explicit first episode number for this disc.")
    parser.add_argument("--count", type=int, default=None, help="Maximum number of episodes to rip from this disc.")
    parser.add_argument("--library", default="/mnt/media/Shows", help="Jellyfin shows library path. Default: /mnt/media/Shows")
    parser.add_argument("--ai", default="llama3:8b")
    parser.add_argument("--device", default="/dev/sr0")
    parser.add_argument("--staging", default=str(Path.home() / "rips/staging"))
    parser.add_argument("--stage-only", action="store_true", help="Rip and validate, but do not move to HDD.")
    parser.add_argument("--no-auto-rerip", action="store_true", help="Disable one-time rerip recovery.")
    parser.add_argument("--allow-extra-candidates", action="store_true", help="Override guard when disc has more episode-looking titles than missing episodes.")
    parser.add_argument("--titles", default=None, help="Comma-separated explicit DVD title numbers in episode order.")
    args = parser.parse_args()

    show = args.show
    season = args.season
    library = Path(args.library)
    season_dir = library / show / f"Season {season:02d}"
    staging = Path(args.staging)
    validation_file = staging / "validation_result.json"

    print("===== JARVIS GUARDED DISC INGEST V2 =====")
    print(f"Show: {show}")
    print(f"Season: {season:02d}")
    print(f"Disc argument: {args.disc}")
    print(f"Library: {library}")
    print(f"AI reviewer: {args.ai}")
    print(f"Auto-rerip: {'OFF' if args.no_auto_rerip else 'ON'}")
    print(f"Stage-only: {'ON' if args.stage_only else 'OFF'}")
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

    five_chapter_episode_shows = {
        "the boondocks",
        "hogan's heroes",
        "hogans heroes",
        "danny phantom",
        "avatar the last airbender",
        "spongebob squarepants",
        "fairly oddparents",
        "the fairly oddparents",
    }

    normalized_show = args.show.strip().lower()
    is_five_chapter_episode_show = normalized_show in five_chapter_episode_shows

    if is_five_chapter_episode_show:
        allowed_chapter_counts = {5}

        if normalized_show in {"hogan's heroes", "hogans heroes"}:
            allowed_chapter_counts.add(7)

        promoted = [
            t for t in extras
            if (t.get("chapters") or 0) in allowed_chapter_counts
        ]

        if promoted:
            print("===== EPISODE CHAPTER-COUNT RECOVERY =====")
            print(
                f"Promoting {len(promoted)} titles with chapter counts "
                f"{sorted(allowed_chapter_counts)} from extras to episode candidates."
            )
            candidates = sorted(
                candidates + promoted,
                key=lambda t: t["title"],
            )
            extras = [t for t in extras if t not in promoted]

    fingerprint = make_fingerprint(
        show,
        season,
        label,
        titles,
        device=args.device,
        disc=args.disc,
    )

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

        print("Some prior mapped episodes are missing, continuing cautiously.")
        print("")

    if args.titles:
        requested_titles = [
            int(x.strip())
            for x in args.titles.split(",")
            if x.strip()
        ]

        by_title = {
            int(t["title"]): t
            for t in titles
        }

        unavailable = [
            n
            for n in requested_titles
            if n not in by_title
        ]

        if unavailable:
            print("===== SAFETY BLOCK =====")
            print(
                f"Explicit DVD titles not found: {unavailable}"
            )
            print("No rip was started.")
            raise SystemExit(1)

        candidates = [
            by_title[n]
            for n in requested_titles
        ]

        print("===== EXPLICIT TITLE OVERRIDE =====")
        print(
            "Requested titles:",
            ", ".join(str(n) for n in requested_titles)
        )
        print(
            "Candidate order:",
            ", ".join(str(t["title"]) for t in candidates)
        )
        print("")

    print("===== CANDIDATE DURATION GUARD =====")

    duration_checked_candidates = []

    for candidate in candidates:
        title_number = candidate["title"]

        duration_seconds = scan_title_duration_seconds(
            args.device,
            title_number,
        )

        candidate["duration_seconds"] = duration_seconds

        if duration_seconds is None:
            print(
                f"REVIEW: Title {title_number} duration could not be verified; "
                "removing it from automatic episode candidates."
            )
            extras.append(candidate)
            continue

        if duration_seconds < 300:
            print(
                f"SKIP: Title {title_number} is under 5 minutes "
                f"({human_duration(duration_seconds)})."
            )
            extras.append(candidate)
            continue

        print(
            f"KEEP: Title {title_number} duration "
            f"{human_duration(duration_seconds)}."
        )
        duration_checked_candidates.append(candidate)

    candidates = duration_checked_candidates
    print(f"Candidates remaining after duration guard: {len(candidates)}")
    print("")

    if not candidates:
        print("ERROR: No episode candidates remain after duration filtering.")
        raise SystemExit(1)

    if len(candidates) > len(missing) and not args.allow_extra_candidates:
        print("===== EXTRA CANDIDATE RECOVERY =====")
        print("This disc has more episode-looking titles than episodes missing.")
        print(f"Episode-looking titles found: {len(candidates)}")
        print(f"Missing episodes remaining: {len(missing)}")
        print("")
        print("Scanning candidate title durations to filter extras...")

        short_episode_shows = {
            "the boondocks",
            "hogan's heroes",
            "hogans heroes",
            "danny phantom",
            "avatar the last airbender",
            "spongebob squarepants",
            "fairly oddparents",
            "the fairly oddparents",
        }

        is_short_episode_show = normalized_show in short_episode_shows

        if is_short_episode_show:
            min_episode_seconds = 18 * 60
            max_episode_seconds = 30 * 60
        else:
            min_episode_seconds = 35 * 60
            max_episode_seconds = 58 * 60

        duration_scanned = []
        for t in candidates:
            duration = scan_title_duration_seconds(args.device, t["title"])
            t["duration_seconds"] = duration
            duration_scanned.append(t)

            status = "KEEP" if duration is not None and min_episode_seconds <= duration <= max_episode_seconds else "DROP"
            print(f"  Title {t['title']} - {human_duration(duration)} - {status}")

        filtered = [
            t for t in duration_scanned
            if t.get("duration_seconds") is not None
            and min_episode_seconds <= t["duration_seconds"] <= max_episode_seconds
        ]

        if len(filtered) == len(missing):
            print("")
            print("✅ Extra candidate recovery succeeded.")
            print("Filtered out short/invalid extras and kept exactly the missing episode count.")
            candidates = filtered
        else:
            print("")
            print("===== SAFETY BLOCK =====")
            print("🚫 Could not safely reduce candidate titles to the missing episode count.")
            print(f"Filtered episode-like titles: {len(filtered)}")
            print(f"Missing episodes remaining: {len(missing)}")
            print("")
            print("No rip was started. No files were moved.")
            print("Manual review is still required.")
            raise SystemExit(1)

    if args.count is not None:
        candidates = candidates[:args.count]

    if args.start is not None:
        requested = list(range(args.start, args.start + len(candidates)))
        invalid = [ep for ep in requested if ep not in missing]

        if invalid:
            print("===== SAFETY BLOCK =====")
            print(f"Requested episode numbers are not currently missing: {invalid}")
            print("No rip was started.")
            raise SystemExit(1)

        episode_numbers = requested
    else:
        episode_numbers = missing[:len(candidates)]

    candidates = candidates[:len(episode_numbers)]

    title_map = {}

    print("===== PROPOSED RIP MAP =====")
    for title, ep_num in zip(candidates, episode_numbers):
        ep_code = f"S{season:02d}E{ep_num:02d}"
        ep_name = next((ep.get("name") for ep in season_eps if ep.get("number") == ep_num), "")
        dest = season_dir / f"{show} - {ep_code}.mkv"

        if dest.exists():
            print(f"🚫 Destination already exists for {ep_code}. Blocking to avoid overwrite.")
            raise SystemExit(1)

        title_map[ep_code] = {
            "title": title["title"],
            "episode_number": ep_num,
            "file_name": f"{show} - {ep_code}.mkv",
        }

        print(f"Title {title['title']} -> {ep_code} - {ep_name} [RIP]")

    print("")
    if os.environ.get("JARVIS_AUTO_CONFIRM", "").strip().upper() == "YES":
        confirm = "YES"
        print("Automatic approval enabled for trusted Caleb ingest.")
    else:
        confirm = input("Proceed with guarded V2 rip/validate/move? Type YES: ")
    if confirm != "YES":
        print("Cancelled.")
        return

    staging.mkdir(parents=True, exist_ok=True)
    for f in staging.glob("*"):
        if f.is_file():
            f.unlink()

    print("")
    print("===== RIPPING TO STAGING =====")
    for ep_code, info in title_map.items():
        out = staging / info["file_name"]
        print(f"\nRipping {ep_code} from title {info['title']}")
        rip_title(args.device, info["title"], out)

    start_ep = episode_numbers[0]
    end_ep = episode_numbers[-1]

    print("")
    print("===== VALIDATING WITH JARVIS =====")
    result = run_validation(show, season, start_ep, end_ep, staging, validation_file, args.ai)

    if result.get("final_result") != "PASS" and not args.no_auto_rerip:
        print("")
        print("===== AUTO-RERIP RECOVERY =====")

        rerip_candidates = result.get("rerip_candidates") or []
        if not rerip_candidates:
            print("No explicit rerip candidates listed. Auto-rerip skipped.")
        else:
            for item in rerip_candidates:
                ep_code = item.get("episode")
                if ep_code not in title_map:
                    print(f"Skipping {ep_code}: no title map found.")
                    continue

                info = title_map[ep_code]
                out = staging / info["file_name"]
                bad_copy = staging / f"{out.stem}.bad_before_rerip{out.suffix}"

                if out.exists():
                    out.rename(bad_copy)
                    print(f"Saved bad copy: {bad_copy}")

                print(f"Auto-reripping {ep_code} from title {info['title']} once...")
                rip_title(args.device, info["title"], out)

            print("")
            print("===== RE-VALIDATING AFTER AUTO-RERIP =====")
            result = run_validation(show, season, start_ep, end_ep, staging, validation_file, args.ai)

    if result.get("final_result") != "PASS":
        print("")
        print("🚫 FINAL RESULT IS NOT PASS. MOVE BLOCKED.")
        print(f"Final result: {result.get('final_result')}")
        print(f"Validation file: {validation_file}")
        raise SystemExit(1)

    if args.stage_only:
        print("")
        print("===== STAGE-ONLY COMPLETE =====")
        print("Rip and validation passed, but files were NOT moved to HDD.")
        print(f"Staged files: {staging}")
        run_cmd(["ls", "-lh", str(staging)], check=False)
        return

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
        "episodes": list(title_map.keys()),
        "title_map": [
            {"title": info["title"], "episode": ep_code}
            for ep_code, info in title_map.items()
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
