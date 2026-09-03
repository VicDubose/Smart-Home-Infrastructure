#!/usr/bin/env python3

import argparse
import json
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
ROUTER = HOME / "rdp-scripts/Jarvis/media/jarvis_movie_arm_router.py"
VIDEO_EXTENSIONS = {".mkv", ".mp4", ".m4v"}

parser = argparse.ArgumentParser(
    description="Run exactly one staged Blu-ray movie through Jarvis."
)
parser.add_argument("--source", required=True, type=Path)
args = parser.parse_args()

job_root = args.source.resolve()
manifest_path = job_root / "job.json"

if not job_root.is_dir():
    print(f"BLOCK: Staged Blu-ray job is missing: {job_root}")
    raise SystemExit(2)

if not manifest_path.is_file():
    print(f"BLOCK: Job manifest is missing: {manifest_path}")
    raise SystemExit(2)

if not ROUTER.is_file():
    print(f"BLOCK: Movie router is missing: {ROUTER}")
    raise SystemExit(2)

try:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as error:
    print(f"BLOCK: Invalid job manifest: {error}")
    raise SystemExit(2)

title = str(manifest.get("title", "")).strip()
year = manifest.get("year")

if not title:
    print("BLOCK: Job manifest has no movie title.")
    raise SystemExit(2)

display = f"{title} ({year})" if year else title
movie_folder = job_root / display

if not movie_folder.is_dir():
    legacy_media = job_root / "media"

    if legacy_media.is_dir():
        legacy_media.rename(movie_folder)
    else:
        print(f"BLOCK: Movie media folder is missing: {movie_folder}")
        raise SystemExit(2)

media_files = [
    path
    for path in movie_folder.rglob("*")
    if path.is_file()
    and path.suffix.casefold() in VIDEO_EXTENSIONS
]

if not media_files:
    print(f"BLOCK: No movie files exist inside: {movie_folder}")
    raise SystemExit(2)

command = [
    sys.executable,
    "-u",
    str(ROUTER),
    "--source",
    str(movie_folder),
    "--commit",
]

process = subprocess.run(
    command,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    check=False,
)

output = process.stdout or ""
print(output, end="")

if process.returncode != 0:
    raise SystemExit(process.returncode)

try:
    payload = json.loads(output)
except json.JSONDecodeError:
    print("BLOCK: Movie router returned invalid JSON.")
    raise SystemExit(2)

results = payload.get("results", [])

if not results:
    print("BLOCK: Movie router returned no result.")
    raise SystemExit(2)

statuses = {
    str(result.get("status", "REVIEW")).upper()
    for result in results
}

if statuses <= {"PASS"}:
    print("BLURAY_RESULT=PASS")
    raise SystemExit(0)

if statuses <= {"SKIP"}:
    print("BLURAY_RESULT=DUPLICATE")
    print("Already imported; no rip needed.")
    raise SystemExit(2)

if "RERIP" in statuses:
    print("BLURAY_RESULT=RERIP")
    raise SystemExit(4)

if "BLOCK" in statuses:
    print("BLURAY_RESULT=BLOCK")
    raise SystemExit(2)

print("BLURAY_RESULT=REVIEW")
raise SystemExit(3)
