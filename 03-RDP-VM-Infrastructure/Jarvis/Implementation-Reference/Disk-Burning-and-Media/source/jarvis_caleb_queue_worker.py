#!/usr/bin/env python3

import fcntl
import hashlib
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
MEDIA_ROOT = Path("/mnt/media")
LIBRARY_ROOT = MEDIA_ROOT / "Shows"

PIPELINE = (
    HOME
    / "rdp-scripts/Jarvis/media/jarvis_disc_ingest_guarded_v2.py"
)

PROFILE_FILE = HOME / "Jarvis/config/caleb_show_profiles.json"

STATE_ROOT = HOME / "Jarvis/state/caleb-auto-ingest"
JOB_ROOT = HOME / "Jarvis/jobs/caleb-auto-ingest"
LOG_ROOT = HOME / "Jarvis/logs/caleb-auto-ingest"
REPORT_ROOT = HOME / "Jarvis/reports/caleb-auto-ingest"
QUARANTINE_ROOT = HOME / "Jarvis/quarantine/caleb-auto-ingest"

REGISTRY_FILE = STATE_ROOT / "processed_registry.json"
LOCK_FILE = Path("/tmp/jarvis_caleb_queue_worker.lock")

IDLE_WAIT_SECONDS = 20 * 60
MAX_MEDIA_USAGE_PERCENT = 85
DEFAULT_AI_MODEL = "phi3:mini"

ACTIVE_PROCESS_PATTERNS = [
    "HandBrakeCLI",
    "dvdbackup",
    "makemkv",
    "MakeMKV",
    "ffmpeg",
    "abcde",
    "cdparanoia",
    "growisofs",
    "wodim",
    "brasero",
    "k3b",
    "jarvis_disc_auto_ingest",
    "jarvis_disc_ingest_guarded",
    "process_caleb_hogans_raw",
]


for directory in [
    STATE_ROOT,
    JOB_ROOT,
    LOG_ROOT,
    REPORT_ROOT,
    QUARANTINE_ROOT,
]:
    directory.mkdir(parents=True, exist_ok=True)


def now_string():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def timestamp():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def log(message=""):
    print(f"[{now_string()}] {message}", flush=True)


def load_json(path, default):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc


def save_json_atomic(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2))
    temporary.replace(path)


def acquire_lock():
    handle = LOCK_FILE.open("w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("Another Caleb queue worker is already running.")
        raise SystemExit(0)

    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def media_usage():
    usage = shutil.disk_usage(MEDIA_ROOT)

    used_percent = (
        (usage.total - usage.free)
        / usage.total
        * 100
    )

    return {
        "total": usage.total,
        "used": usage.total - usage.free,
        "free": usage.free,
        "percent": used_percent,
    }


def human_bytes(value):
    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    amount = float(value)

    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.2f} {unit}"
        amount /= 1024

    return f"{amount:.2f} TiB"


def active_media_processes():
    result = subprocess.run(
        ["ps", "-eo", "pid=,args="],
        capture_output=True,
        text=True,
        check=False,
    )

    current_pid = os.getpid()
    matches = []

    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()

        if not line:
            continue

        parts = line.split(maxsplit=1)

        if len(parts) != 2:
            continue

        try:
            pid = int(parts[0])
        except ValueError:
            continue

        command = parts[1]

        if pid == current_pid:
            continue

        if "jarvis_caleb_queue_worker.py" in command:
            continue

        if any(pattern.lower() in command.lower()
               for pattern in ACTIVE_PROCESS_PATTERNS):
            matches.append(line)

    return matches


def wait_for_idle_window():
    active = active_media_processes()

    if active:
        log("Media activity is already running. Queue worker will exit.")
        for line in active:
            log(f"  Active: {line}")
        return False

    log("No ripping, burning, or encoding detected.")
    log("Waiting 20 minutes before beginning Caleb ingest.")

    time.sleep(IDLE_WAIT_SECONDS)

    active = active_media_processes()

    if active:
        log("Media activity started during the 20-minute waiting period.")
        for line in active:
            log(f"  Active: {line}")
        return False

    log("Server remained idle for the full 20-minute window.")
    return True


def load_profiles():
    data = load_json(PROFILE_FILE, {"profiles": []})
    profiles = data.get("profiles", [])

    if not profiles:
        raise RuntimeError(
            f"No show profiles configured in {PROFILE_FILE}"
        )

    return profiles


def recognize_show(folder_name, profiles):
    for profile in profiles:
        for pattern in profile.get("folder_patterns", []):
            if re.search(pattern, folder_name):
                return profile

    return None


def parse_season_disc(folder_name, default_season):
    season_disc_patterns = [
        r"(?i)[_-]S(?:eason)?[_ -]?(\d+)[_-]D(?:isc)?[_ -]?(\d+)",
        r"(?i)[_-]S(\d+)[_-]D(\d+)",
    ]

    for pattern in season_disc_patterns:
        match = re.search(pattern, folder_name)

        if match:
            return int(match.group(1)), int(match.group(2))

    disc_patterns = [
        r"(?i)[_-]D(?:isc)?[_ -]?(\d+)",
        r"(?i)[_-]D(\d+)",
    ]

    for pattern in disc_patterns:
        match = re.search(pattern, folder_name)

        if match:
            return int(default_season), int(match.group(1))

    return None


def find_video_ts(folder):
    candidates = []

    if folder.name.upper() == "VIDEO_TS":
        candidates.append(folder)

    candidates.extend(
        path
        for path in folder.rglob("*")
        if path.is_dir() and path.name.upper() == "VIDEO_TS"
    )

    for candidate in candidates:
        has_video_ifo = (candidate / "VIDEO_TS.IFO").exists()
        has_title_ifo = bool(list(candidate.glob("VTS_*_0.IFO")))
        has_vob = bool(list(candidate.glob("VTS_*_*.VOB")))

        if has_video_ifo and has_title_ifo and has_vob:
            return candidate

    return None


def folder_size(folder):
    total = 0

    for path in folder.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue

    return total


def source_fingerprint(folder, video_ts):
    digest = hashlib.sha256()
    digest.update(str(folder.resolve()).encode())

    files = sorted(
        path
        for path in video_ts.iterdir()
        if path.is_file()
    )

    for path in files:
        stat = path.stat()
        digest.update(path.name.encode())
        digest.update(str(stat.st_size).encode())
        digest.update(str(stat.st_mtime_ns).encode())

    return digest.hexdigest()[:24]


def discover_jobs(profiles, registry):
    selected = {}
    rejected = []

    if not SOURCE_ROOT.exists():
        raise RuntimeError(f"Caleb source path is missing: {SOURCE_ROOT}")

    for folder in sorted(SOURCE_ROOT.iterdir()):
        if not folder.is_dir():
            continue

        if folder.name.endswith(".receiving"):
            rejected.append({
                "folder": str(folder),
                "status": "incomplete_transfer",
                "reason": "Folder still ends in .receiving",
            })
            continue

        profile = recognize_show(folder.name, profiles)

        if profile is None:
            rejected.append({
                "folder": str(folder),
                "status": "unknown_show",
                "reason": "No matching show profile",
            })
            continue

        identity = parse_season_disc(
            folder.name,
            profile.get("default_season", 1),
        )

        if identity is None:
            rejected.append({
                "folder": str(folder),
                "status": "unrecognized_disc_number",
                "reason": "Could not determine season and disc",
            })
            continue

        season, disc = identity
        video_ts = find_video_ts(folder)

        if video_ts is None:
            rejected.append({
                "folder": str(folder),
                "status": "invalid_raw_structure",
                "reason": "Complete VIDEO_TS structure was not found",
            })
            continue

        fingerprint = source_fingerprint(folder, video_ts)

        if fingerprint in registry.get("passed", {}):
            continue

        size = folder_size(folder)
        key = (
            profile["name"].lower(),
            season,
            disc,
        )

        candidate = {
            "show": profile["name"],
            "season": season,
            "disc": disc,
            "ai_model": profile.get(
                "ai_model",
                DEFAULT_AI_MODEL,
            ),
            "folder": folder,
            "video_ts": video_ts,
            "size": size,
            "fingerprint": fingerprint,
        }

        existing = selected.get(key)

        if existing is None or size > existing["size"]:
            if existing is not None:
                rejected.append({
                    "folder": str(existing["folder"]),
                    "status": "duplicate_raw_copy",
                    "reason": (
                        f"Smaller duplicate of "
                        f"{profile['name']} "
                        f"S{season:02d}D{disc:02d}"
                    ),
                })

            selected[key] = candidate
        else:
            rejected.append({
                "folder": str(folder),
                "status": "duplicate_raw_copy",
                "reason": (
                    f"Smaller duplicate of "
                    f"{profile['name']} "
                    f"S{season:02d}D{disc:02d}"
                ),
            })

    jobs = sorted(
        selected.values(),
        key=lambda item: (
            item["show"].lower(),
            item["season"],
            item["disc"],
            item["folder"].stat().st_mtime,
        ),
    )

    return jobs, rejected


def write_failure_report(job, validation, reason, log_path):
    report = {
        "generated_at": datetime.now().isoformat(),
        "show": job["show"],
        "season": job["season"],
        "disc": job["disc"],
        "raw_folder": str(job["folder"]),
        "video_ts": str(job["video_ts"]),
        "fingerprint": job["fingerprint"],
        "reason": reason,
        "validation": validation,
        "pipeline_log": str(log_path),
        "raw_source_deleted": False,
    }

    report_name = (
        f"{job['show'].replace(' ', '_')}"
        f"-S{job['season']:02d}"
        f"-D{job['disc']:02d}"
        f"-{timestamp()}.json"
    )

    report_path = QUARANTINE_ROOT / report_name
    report_path.write_text(json.dumps(report, indent=2))

    return report_path


def delete_failed_encode_artifacts(staging, deleted_records):
    patterns = [
        "*.bad_before_rerip.mkv",
        "*.premature-*.mkv",
        "*.rerip.tmp.mkv",
        "*.failed.mkv",
        "*.corrupt.mkv",
        "*.partial.mkv",
    ]

    for pattern in patterns:
        for path in staging.glob(pattern):
            try:
                record = {
                    "path": str(path),
                    "size": path.stat().st_size,
                    "deleted_at": datetime.now().isoformat(),
                }

                path.unlink()
                deleted_records.append(record)
                log(f"Deleted replaced failed encode: {path.name}")

            except OSError as exc:
                log(f"Could not delete failed artifact {path}: {exc}")


def run_job(job, registry):
    safe_show = re.sub(r"[^A-Za-z0-9._-]+", "_", job["show"])
    job_id = (
        f"{safe_show}"
        f"-S{job['season']:02d}"
        f"-D{job['disc']:02d}"
        f"-{timestamp()}"
    )

    staging = JOB_ROOT / job_id
    staging.mkdir(parents=True, exist_ok=True)

    log_path = LOG_ROOT / f"{job_id}.log"
    validation_path = staging / "validation_result.json"

    command = [
        sys.executable,
        "-u",
        str(PIPELINE),
        "--show",
        job["show"],
        "--season",
        str(job["season"]),
        "--disc",
        str(job["disc"]),
        "--device",
        str(job["video_ts"]),
        "--library",
        str(LIBRARY_ROOT),
        "--staging",
        str(staging),
        "--ai",
        job["ai_model"],
    ]

    log("")
    log("=" * 72)
    log(
        f"Processing {job['show']} "
        f"S{job['season']:02d} Disc {job['disc']:02d}"
    )
    log(f"Raw source: {job['video_ts']}")
    log(f"Raw size: {human_bytes(job['size'])}")
    log(f"AI reviewer: {job['ai_model']}")
    log("=" * 72)

    environment = os.environ.copy()
    environment["TERM"] = "dumb"
    environment["NO_COLOR"] = "1"

    with log_path.open("w", encoding="utf-8") as output_log:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=environment,
            bufsize=1,
        )

        assert process.stdin is not None
        assert process.stdout is not None

        process.stdin.write("YES\n")
        process.stdin.flush()
        process.stdin.close()

        for line in process.stdout:
            sys.stdout.write(line)
            output_log.write(line)
            output_log.flush()

        return_code = process.wait()

    validation = None

    if validation_path.exists():
        try:
            validation = json.loads(validation_path.read_text())
        except json.JSONDecodeError as exc:
            log(f"Validation JSON could not be read: {exc}")

    final_result = (
        validation.get("final_result")
        if isinstance(validation, dict)
        else None
    )

    technical_result = (
        validation.get("technical_result")
        if isinstance(validation, dict)
        else None
    )

    ai_review = (
        validation.get("ai_review") or {}
        if isinstance(validation, dict)
        else {}
    )

    ai_result = ai_review.get("ai_result")

    if (
        return_code == 0
        and technical_result == "PASS"
        and ai_result == "PASS"
        and final_result == "PASS"
    ):
        deleted_records = []
        delete_failed_encode_artifacts(staging, deleted_records)

        registry.setdefault("passed", {})[job["fingerprint"]] = {
            "show": job["show"],
            "season": job["season"],
            "disc": job["disc"],
            "source": str(job["folder"]),
            "video_ts": str(job["video_ts"]),
            "processed_at": datetime.now().isoformat(),
            "validation": str(validation_path),
            "log": str(log_path),
            "deleted_failed_artifacts": deleted_records,
            "raw_source_deleted": False,
        }

        registry.get("failed", {}).pop(job["fingerprint"], None)
        save_json_atomic(REGISTRY_FILE, registry)

        log(
            f"PASS: {job['show']} "
            f"S{job['season']:02d}D{job['disc']:02d} "
            f"was moved into Jellyfin."
        )

        return "PASS"

    reason = (
        f"Pipeline return code={return_code}; "
        f"technical={technical_result}; "
        f"AI={ai_result}; "
        f"final={final_result}"
    )

    failure_report = write_failure_report(
        job,
        validation,
        reason,
        log_path,
    )

    registry.setdefault("failed", {})[job["fingerprint"]] = {
        "show": job["show"],
        "season": job["season"],
        "disc": job["disc"],
        "source": str(job["folder"]),
        "failed_at": datetime.now().isoformat(),
        "reason": reason,
        "report": str(failure_report),
        "raw_source_deleted": False,
    }

    save_json_atomic(REGISTRY_FILE, registry)

    log(
        f"REVIEW/BLOCK: {job['show']} "
        f"S{job['season']:02d}D{job['disc']:02d}"
    )
    log(f"Failure report: {failure_report}")

    return "FAILED"


def main():
    lock_handle = acquire_lock()

    try:
        log("=" * 72)
        log("JARVIS CALEB AUTOMATIC RAW-RIP QUEUE")
        log("=" * 72)

        if not PIPELINE.exists():
            raise RuntimeError(f"Jarvis TV pipeline is missing: {PIPELINE}")

        if not MEDIA_ROOT.is_mount():
            raise RuntimeError(
                f"{MEDIA_ROOT} is not currently mounted. "
                "Automatic ingest stopped."
            )

        usage = media_usage()

        log(
            f"Jellyfin storage: "
            f"{usage['percent']:.2f}% used; "
            f"{human_bytes(usage['free'])} free"
        )

        if usage["percent"] >= MAX_MEDIA_USAGE_PERCENT:
            log(
                f"Storage is already at or above "
                f"{MAX_MEDIA_USAGE_PERCENT}%. Nothing will be processed."
            )
            return

        if not wait_for_idle_window():
            return

        profiles = load_profiles()

        registry = load_json(
            REGISTRY_FILE,
            {
                "passed": {},
                "failed": {},
            },
        )

        jobs, rejected = discover_jobs(profiles, registry)

        discovery_report = {
            "generated_at": datetime.now().isoformat(),
            "queued_jobs": [
                {
                    **{
                        key: value
                        for key, value in job.items()
                        if key not in {"folder", "video_ts"}
                    },
                    "folder": str(job["folder"]),
                    "video_ts": str(job["video_ts"]),
                }
                for job in jobs
            ],
            "rejected": rejected,
        }

        discovery_path = (
            REPORT_ROOT
            / f"queue-discovery-{timestamp()}.json"
        )

        discovery_path.write_text(
            json.dumps(discovery_report, indent=2)
        )

        log(f"Eligible completed raw rips: {len(jobs)}")
        log(f"Skipped/incomplete/unknown folders: {len(rejected)}")
        log(f"Discovery report: {discovery_path}")

        if not jobs:
            log("There are no eligible Caleb raw rips waiting.")
            return

        passed = 0
        failed = 0

        for job in jobs:
            usage = media_usage()

            if usage["percent"] >= MAX_MEDIA_USAGE_PERCENT:
                log(
                    f"Stopping queue: /mnt/media reached "
                    f"{usage['percent']:.2f}% usage."
                )
                break

            active = active_media_processes()

            if active:
                log(
                    "Another media process started. "
                    "Stopping this queue safely."
                )
                for line in active:
                    log(f"  Active: {line}")
                break

            result = run_job(job, registry)

            if result == "PASS":
                passed += 1
            else:
                failed += 1

            usage = media_usage()

            log(
                f"Storage after job: "
                f"{usage['percent']:.2f}% used; "
                f"{human_bytes(usage['free'])} free"
            )

            if usage["percent"] >= MAX_MEDIA_USAGE_PERCENT:
                log("The 85% storage limit has been reached.")
                break

            log("Cooling server for 60 seconds before the next raw disc.")
            time.sleep(60)

        final_usage = media_usage()

        summary = {
            "generated_at": datetime.now().isoformat(),
            "passed_this_run": passed,
            "failed_this_run": failed,
            "storage_percent": round(final_usage["percent"], 2),
            "storage_free_bytes": final_usage["free"],
            "storage_limit_percent": MAX_MEDIA_USAGE_PERCENT,
            "registry": str(REGISTRY_FILE),
        }

        summary_path = (
            REPORT_ROOT
            / f"run-summary-{timestamp()}.json"
        )

        summary_path.write_text(json.dumps(summary, indent=2))

        log("")
        log("===== FINAL RUN SUMMARY =====")
        log(f"Passed: {passed}")
        log(f"Failed or corrupted: {failed}")
        log(
            f"Jellyfin storage: "
            f"{final_usage['percent']:.2f}% used"
        )
        log(f"Summary: {summary_path}")

    finally:
        lock_handle.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("Queue worker interrupted safely.")
        raise SystemExit(130)
    except Exception as exc:
        log(f"FATAL: {exc}")
        raise
