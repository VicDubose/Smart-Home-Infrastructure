#!/usr/bin/env python3

import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HOME = Path.home()
SOURCE_ROOT = Path("/mnt/appdata/caleb-media/incoming/DVD")
PIPELINE = HOME / "rdp-scripts/Jarvis/media/jarvis_disc_ingest_guarded_v2.py"
RUN_ROOT = HOME / "Jarvis/jobs/hogans"
LOG_ROOT = HOME / "Jarvis/logs/hogans-raw-batch"
REPORT_ROOT = HOME / "Jarvis/reports"
LIBRARY_ROOT = Path("/mnt/media/Shows/Hogan's Heroes")

STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
MASTER_LOG = LOG_ROOT / f"hogans-raw-batch-{STAMP}.log"
BAD_REPORT = REPORT_ROOT / f"hogans-bad-files-{STAMP}.txt"
JSON_REPORT = REPORT_ROOT / f"hogans-batch-{STAMP}.json"

LOG_ROOT.mkdir(parents=True, exist_ok=True)
REPORT_ROOT.mkdir(parents=True, exist_ok=True)
RUN_ROOT.mkdir(parents=True, exist_ok=True)


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for stream in self.streams:
            stream.write(data)
            stream.flush()

    def flush(self):
        for stream in self.streams:
            stream.flush()


log_handle = MASTER_LOG.open("a", encoding="utf-8")
sys.stdout = Tee(sys.__stdout__, log_handle)
sys.stderr = Tee(sys.__stderr__, log_handle)


def folder_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            pass
    return total


def identify(folder_name: str):
    match = re.search(
        r"[Ss](\d+)[_-][Dd](?:isc[_-]?)?(\d+)",
        folder_name,
        re.IGNORECASE,
    )
    if match:
        return int(match.group(1)), int(match.group(2))

    match = re.search(
        r"^HOGANS_HEROES_D(\d+)",
        folder_name,
        re.IGNORECASE,
    )
    if match:
        return 1, int(match.group(1))

    return None


def find_video_ts(folder: Path):
    candidates = [
        path for path in folder.rglob("*")
        if path.is_dir() and path.name.upper() == "VIDEO_TS"
    ]

    for candidate in candidates:
        if (
            (candidate / "VIDEO_TS.IFO").exists()
            and list(candidate.glob("VTS_*_*.IFO"))
            and list(candidate.glob("VTS_*_*.VOB"))
        ):
            return candidate

    return None


def active_media_job():
    result = subprocess.run(
        [
            "pgrep", "-af",
            "jarvis_disc_ingest_guarded|HandBrakeCLI|ffmpeg|dvdbackup|makemkv"
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    lines = [
        line for line in result.stdout.splitlines()
        if "process_caleb_hogans_raw.py" not in line
    ]
    return lines


def delete_known_bad_files(staging: Path, bad_records: list):
    patterns = [
        "*.bad_before_rerip.mkv",
        "*.premature-*.mkv",
        "*.rerip.tmp.mkv",
        "*.failed.mkv",
        "*.corrupt.mkv",
    ]

    for pattern in patterns:
        for path in staging.glob(pattern):
            try:
                size = path.stat().st_size
                bad_records.append({
                    "type": "deleted_failed_encode",
                    "path": str(path),
                    "size": size,
                })
                path.unlink()
                print(f"DELETED BAD ARTIFACT: {path}")
            except OSError as exc:
                bad_records.append({
                    "type": "delete_failed",
                    "path": str(path),
                    "reason": str(exc),
                })


print("=" * 78)
print("JARVIS — CALEB RAW HOGAN'S HEROES INGEST")
print("=" * 78)
print(f"Started: {datetime.now()}")
print(f"Raw source: {SOURCE_ROOT}")
print(f"AI reviewer: phi3:mini")
print(f"Master log: {MASTER_LOG}")

active = active_media_job()
if active:
    print("\nERROR: Another media job is active:")
    for line in active:
        print(line)
    raise SystemExit(1)

if not PIPELINE.exists():
    raise SystemExit(f"Pipeline missing: {PIPELINE}")

selected = {}
bad_records = []
skipped = []

print("\n===== DISCOVERING EXISTING RAW RIPS =====")

for folder in sorted(SOURCE_ROOT.iterdir()):
    if not folder.is_dir() or "hogan" not in folder.name.lower():
        continue

    if folder.name.endswith(".receiving"):
        record = {
            "type": "incomplete_transfer",
            "path": str(folder),
            "reason": "Folder still has .receiving suffix",
        }
        bad_records.append(record)
        skipped.append(record)
        print(f"SKIP INCOMPLETE: {folder.name}")
        continue

    identity = identify(folder.name)
    if not identity:
        record = {
            "type": "unrecognized_folder",
            "path": str(folder),
            "reason": "Could not determine season and disc from folder name",
        }
        bad_records.append(record)
        skipped.append(record)
        print(f"SKIP UNRECOGNIZED: {folder.name}")
        continue

    season, disc = identity
    video_ts = find_video_ts(folder)

    if video_ts is None:
        record = {
            "type": "invalid_raw_dvd",
            "path": str(folder),
            "reason": "No complete VIDEO_TS structure found",
        }
        bad_records.append(record)
        skipped.append(record)
        print(f"SKIP BAD RAW STRUCTURE: {folder.name}")
        continue

    size = folder_size(folder)
    key = (season, disc)

    current = selected.get(key)
    if current is None or size > current["size"]:
        if current is not None:
            bad_records.append({
                "type": "duplicate_raw_copy",
                "path": str(current["folder"]),
                "reason": f"Smaller duplicate of S{season:02d}D{disc:02d}",
                "size": current["size"],
            })

        selected[key] = {
            "folder": folder,
            "video_ts": video_ts,
            "size": size,
        }
    else:
        bad_records.append({
            "type": "duplicate_raw_copy",
            "path": str(folder),
            "reason": f"Smaller duplicate of S{season:02d}D{disc:02d}",
            "size": size,
        })

if not selected:
    raise SystemExit("No valid completed Hogan's Heroes raw DVD folders found.")

print("\n===== SELECTED RAW SOURCES =====")
for (season, disc), source in sorted(selected.items()):
    print(
        f"S{season:02d}D{disc:02d} "
        f"{source['size'] / (1024**3):.2f} GiB "
        f"{source['video_ts']}"
    )

results = []

for (season, disc), source in sorted(selected.items()):
    job_id = f"S{season:02d}D{disc:02d}-{STAMP}"
    staging = RUN_ROOT / job_id
    log_path = LOG_ROOT / f"{job_id}.log"
    staging.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 78)
    print(f"PROCESSING S{season:02d} DISC {disc:02d}")
    print(f"Raw VIDEO_TS: {source['video_ts']}")
    print(f"Staging: {staging}")
    print("=" * 78)

    command = [
        sys.executable,
        "-u",
        str(PIPELINE),
        "--show", "Hogan's Heroes",
        "--season", str(season),
        "--disc", str(disc),
        "--device", str(source["video_ts"]),
        "--library", "/mnt/media/Shows",
        "--staging", str(staging),
        "--ai", "phi3:mini",
    ]

    env = os.environ.copy()
    env["TERM"] = "dumb"
    env["NO_COLOR"] = "1"

    with log_path.open("w", encoding="utf-8") as disc_log:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            bufsize=1,
        )

        assert process.stdin is not None
        assert process.stdout is not None

        process.stdin.write("YES\n")
        process.stdin.flush()
        process.stdin.close()

        for line in process.stdout:
            print(line, end="")
            disc_log.write(line)
            disc_log.flush()

        return_code = process.wait()

    validation_file = staging / "validation_result.json"
    validation = None

    if validation_file.exists():
        try:
            validation = json.loads(validation_file.read_text())
        except Exception as exc:
            bad_records.append({
                "type": "invalid_validation_json",
                "path": str(validation_file),
                "reason": str(exc),
            })

    final_result = (
        validation.get("final_result")
        if isinstance(validation, dict)
        else None
    )

    result = {
        "season": season,
        "disc": disc,
        "raw_folder": str(source["folder"]),
        "video_ts": str(source["video_ts"]),
        "staging": str(staging),
        "log": str(log_path),
        "return_code": return_code,
        "final_result": final_result or "UNKNOWN",
    }

    if final_result == "PASS":
        print(f"PASS: S{season:02d}D{disc:02d} validated and moved.")
        delete_known_bad_files(staging, bad_records)
        result["status"] = "passed"
    else:
        print(f"REVIEW/BLOCK: S{season:02d}D{disc:02d}")

        result["status"] = "blocked"

        if validation:
            for item in validation.get("checks", []):
                if item.get("status") != "PASS":
                    bad_records.append({
                        "type": "validation_failure",
                        "season": season,
                        "disc": disc,
                        "episode": item.get("episode"),
                        "path": item.get("file"),
                        "classification": item.get("classification"),
                        "warnings": item.get("warnings", []),
                    })
        else:
            bad_records.append({
                "type": "pipeline_failure",
                "season": season,
                "disc": disc,
                "path": str(source["folder"]),
                "reason": f"No usable PASS validation; return code {return_code}",
            })

    results.append(result)

    # Let the compact server cool briefly between encodes.
    time.sleep(30)

report = {
    "generated_at": datetime.now().isoformat(),
    "source_root": str(SOURCE_ROOT),
    "ai_model": "phi3:mini",
    "results": results,
    "bad_files": bad_records,
}

JSON_REPORT.write_text(json.dumps(report, indent=2))

with BAD_REPORT.open("w", encoding="utf-8") as handle:
    handle.write("JARVIS HOGAN'S HEROES BAD / SKIPPED FILE REPORT\n")
    handle.write(f"Generated: {datetime.now()}\n\n")

    for item in bad_records:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")

print("\n" + "=" * 78)
print("FINAL HOGAN'S HEROES LIBRARY")
print("=" * 78)

if LIBRARY_ROOT.exists():
    for path in sorted(LIBRARY_ROOT.rglob("*.mkv")):
        print(path.relative_to(LIBRARY_ROOT))
else:
    print("No Hogan's Heroes library folder exists yet.")

print("\n===== BATCH SUMMARY =====")
print(f"Passed:  {sum(r['status'] == 'passed' for r in results)}")
print(f"Blocked: {sum(r['status'] == 'blocked' for r in results)}")
print(f"Bad/skipped records: {len(bad_records)}")
print(f"Bad-file list: {BAD_REPORT}")
print(f"JSON report: {JSON_REPORT}")
print(f"Master log: {MASTER_LOG}")
print(f"Completed: {datetime.now()}")
