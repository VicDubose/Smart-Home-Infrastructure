#!/usr/bin/env python3

import argparse
import re
from pathlib import Path


EXPECTED_COUNTS = {
    1: 32,
    2: 30,
    3: 30,
    4: 26,
    5: 13,
}


def scan_season(show_dir, season):
    season_dir = show_dir / f"Season {season:02d}"
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


def main():
    parser = argparse.ArgumentParser(description="Audit Jellyfin show library episode gaps.")
    parser.add_argument("--show", required=True)
    parser.add_argument("--library", required=True)
    args = parser.parse_args()

    show_dir = Path(args.library) / args.show

    print("===== JARVIS LIBRARY AUDIT =====")
    print(f"Show: {args.show}")
    print(f"Path: {show_dir}")
    print("")

    for season, expected_count in EXPECTED_COUNTS.items():
        found = scan_season(show_dir, season)
        expected = list(range(1, expected_count + 1))
        missing = [ep for ep in expected if ep not in found]

        print(f"===== Season {season:02d} =====")
        print(f"Expected episodes: {expected_count}")
        print(f"Found episodes: {len(found)}")

        if found:
            print("Found:")
            print("  " + ", ".join(f"S{season:02d}E{ep:02d}" for ep in found))
        else:
            print("Found: none")

        if missing:
            print("Missing:")
            print("  " + ", ".join(f"S{season:02d}E{ep:02d}" for ep in missing))
        else:
            print("Missing: none")

        print("")


if __name__ == "__main__":
    main()
