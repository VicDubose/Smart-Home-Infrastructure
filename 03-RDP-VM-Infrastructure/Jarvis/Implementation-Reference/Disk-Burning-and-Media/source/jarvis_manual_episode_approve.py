#!/usr/bin/env python3
import argparse, shutil
from pathlib import Path
from datetime import datetime

parser = argparse.ArgumentParser()
parser.add_argument("--show", required=True)
parser.add_argument("--season", type=int, required=True)
parser.add_argument("--episodes", required=True, help="Example: 3,4")
parser.add_argument("--staging", required=True)
parser.add_argument("--library", required=True)
parser.add_argument("--reason", required=True)
args = parser.parse_args()

show = args.show
season = args.season
episodes = [int(x.strip()) for x in args.episodes.split(",")]

staging = Path(args.staging)
dest_dir = Path(args.library) / show / f"Season {season:02d}"
dest_dir.mkdir(parents=True, exist_ok=True)

audit = staging / "manual_episode_approval_audit.txt"

with audit.open("a") as log:
    log.write(f"\n[{datetime.now().isoformat()}] Manual approval\n")
    log.write(f"Show: {show}\nSeason: {season:02d}\nEpisodes: {episodes}\nReason: {args.reason}\n")

    for ep in episodes:
        filename = f"{show} - S{season:02d}E{ep:02d}.mkv"
        src = staging / filename
        dst = dest_dir / filename

        if not src.exists():
            raise FileNotFoundError(f"Missing staging file: {src}")

        if dst.exists():
            raise FileExistsError(f"Destination already exists: {dst}")

        shutil.move(str(src), str(dst))
        log.write(f"Moved: {src} -> {dst}\n")
        print(f"✅ Moved {filename}")

print(f"\nAudit written to: {audit}")
print("Manual approval complete.")
