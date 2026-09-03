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


INCOMING = Path("/mnt/appdata/jarvis-intake/incoming/local-dvd")
ACTIVE = Path("/mnt/appdata/jarvis-intake/active")
VALIDATION = Path("/mnt/appdata/jarvis-intake/validation")
FAILED = Path("/mnt/appdata/jarvis-intake/failed")

LOCK_FILE = Path("/tmp/jarvis-local-dvd.lock")

MIN_MOVIE_SECONDS = 45 * 60
COOLDOWN_SECONDS = 120


def run(command, log_file=None, check=False):
    printable = " ".join(str(item) for item in command)
    print(f"\n$ {printable}", flush=True)

    process = subprocess.run(
        [str(item) for item in command],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    output = process.stdout or ""
    print(output, end="", flush=True)

    if log_file:
        with log_file.open("a", encoding="utf-8") as handle:
            handle.write(f"\n$ {printable}\n")
            handle.write(output)

    if check and process.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {process.returncode}: {printable}"
        )

    return output, process.returncode


def write_manifest(path, manifest):
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def update_status(job_root, message):
    timestamp = datetime.now().astimezone().isoformat()
    text = f"{timestamp}  {message}\n"

    with (job_root / "status.txt").open("a", encoding="utf-8") as handle:
        handle.write(text)

    print(message, flush=True)


def scan_titles(source, scan_log):
    output, returncode = run(
        [
            "HandBrakeCLI",
            "-i",
            source,
            "--title",
            "0",
            "--scan",
        ],
        log_file=scan_log,
        check=False,
    )

    scanned = []
    current_title = None

    for raw_line in output.splitlines():
        line = raw_line.strip()

        title_match = re.match(
            r"\+ title\s+(\d+):",
            line,
            re.IGNORECASE,
        )

        if title_match:
            current_title = int(title_match.group(1))
            continue

        duration_match = re.match(
            r"\+ duration:\s*(\d+):(\d+):(\d+)",
            line,
            re.IGNORECASE,
        )

        if duration_match and current_title is not None:
            hours, minutes, seconds = map(
                int,
                duration_match.groups(),
            )

            scanned.append(
                {
                    "title_number": current_title,
                    "duration_seconds": (
                        hours * 3600
                        + minutes * 60
                        + seconds
                    ),
                    "duration": (
                        f"{hours:02d}:"
                        f"{minutes:02d}:"
                        f"{seconds:02d}"
                    ),
                }
            )

            current_title = None

    if not scanned:
        raise RuntimeError(
            "HandBrake found no valid titles in the staged DVD."
        )

    return scanned


def probe_media(path):
    output, returncode = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-show_entries",
            "stream=codec_type,codec_name",
            "-of",
            "json",
            str(path),
        ],
        check=False,
    )

    if returncode != 0:
        return None

    try:
        data = json.loads(output)
        duration = float(data["format"]["duration"])
        size = int(data["format"]["size"])

        stream_types = {
            stream.get("codec_type")
            for stream in data.get("streams", [])
        }

        return {
            "duration_seconds": duration,
            "size_bytes": size,
            "has_video": "video" in stream_types,
            "has_audio": "audio" in stream_types,
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def acquire_lock():
    try:
        descriptor = os.open(
            LOCK_FILE,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        )
        os.write(descriptor, str(os.getpid()).encode("ascii"))
        os.close(descriptor)
    except FileExistsError:
        print("BLOCK: Another local DVD worker holds the lock.")
        raise SystemExit(2)


def release_lock():
    LOCK_FILE.unlink(missing_ok=True)


def find_next_job():
    candidates = []

    for manifest_path in INCOMING.glob("*/job.json"):
        try:
            manifest = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            continue

        if manifest.get("state") != "ready":
            continue

        candidates.append(
            (
                int(manifest.get("priority", 50)),
                manifest.get("created_at", ""),
                manifest_path.parent,
            )
        )

    if not candidates:
        return None

    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2]


def process_job(incoming_root):
    manifest_path = incoming_root / "job.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    job_id = manifest["job_id"]
    profile = manifest.get("profile")
    device = manifest["source_metadata"]["device"]
    physical_device = device
    expected_items = int(manifest.get("expected_items") or 1)

    if profile not in {"movie", "movie-collection"}:
        raise RuntimeError(
            f"Unsupported proof-of-concept profile: {profile}"
        )

    active_root = ACTIVE / job_id
    validation_root = VALIDATION / job_id

    if active_root.exists():
        raise RuntimeError(f"Active job already exists: {active_root}")

    shutil.move(str(incoming_root), str(active_root))

    manifest_path = active_root / "job.json"
    log_file = active_root / "worker.log"
    scan_log = active_root / "title-scan.log"
    output_root = (
        Path(manifest["staging_path"]) / "encoded"
    )

    output_root.mkdir(parents=True, exist_ok=True)

    manifest["state"] = "active"
    manifest["workflow"]["intake"] = "complete"
    manifest["workflow"]["rip"] = "active"
    manifest["attempts"]["rip"] = (
        int(manifest["attempts"].get("rip", 0)) + 1
    )
    write_manifest(manifest_path, manifest)

    update_status(active_root, "ACTIVE: local DVD worker claimed job")

    current_label_output, _ = run(
        ["lsblk", "-ndo", "LABEL", device],
        log_file=log_file,
        check=False,
    )
    current_label = current_label_output.strip()

    expected_label = (
        manifest.get("source_metadata", {}).get("disc_label") or ""
    ).strip()

    def normalize_disc_label(value):
        return re.sub(
            r"[^a-z0-9]+",
            "",
            str(value).casefold(),
        )

    if (
        expected_label
        and normalize_disc_label(current_label)
        != normalize_disc_label(expected_label)
    ):
        raise RuntimeError(
            f"Wrong disc detected. Expected '{expected_label}', "
            f"found '{current_label or 'none'}'."
        )

    staging_root = Path(manifest["staging_path"])
    raw_parent = staging_root / "raw"

    if raw_parent.exists():
        shutil.rmtree(raw_parent)

    if output_root.exists():
        shutil.rmtree(output_root)

    raw_parent.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    update_status(
        active_root,
        "PREFLIGHT: retrieving DVD information and CSS keys",
    )

    preflight_ok = False

    for attempt in range(1, 4):
        preflight_output, preflight_code = run(
            [
                "dvdbackup",
                "-I",
                "-i",
                physical_device,
            ],
            log_file=log_file,
            check=False,
        )

        if (
            preflight_code == 0
            and "DVD-Video information" in preflight_output
        ):
            preflight_ok = True
            break

        if attempt < 3:
            update_status(
                active_root,
                f"PREFLIGHT RETRY: attempt {attempt}/3 failed",
            )
            time.sleep(8)

    if not preflight_ok:
        raise RuntimeError(
            "DVD preflight failed after three attempts."
        )

    update_status(
        active_root,
        "RAW COPY: copying DVD to local staging",
    )

    copy_output, copy_code = run(
        [
            "dvdbackup",
            "-M",
            "-i",
            physical_device,
            "-o",
            str(raw_parent),
        ],
        log_file=log_file,
        check=False,
    )

    copy_lower = copy_output.casefold()

    if copy_code != 0:
        raise RuntimeError(
            f"dvdbackup exited with code {copy_code}."
        )

    fatal_markers = (
        "error reading",
        "input/output error",
        "failed to read",
        "padding block",
    )

    if any(marker in copy_lower for marker in fatal_markers):
        raise RuntimeError(
            "dvdbackup reported errors during the raw copy."
        )

    video_ts_directories = [
        directory
        for directory in raw_parent.rglob("VIDEO_TS")
        if directory.is_dir()
    ]

    if len(video_ts_directories) != 1:
        raise RuntimeError(
            "Could not locate exactly one staged VIDEO_TS folder."
        )

    video_ts_root = video_ts_directories[0]

    if not (video_ts_root / "VIDEO_TS.IFO").is_file():
        raise RuntimeError(
            "Staged DVD is missing VIDEO_TS.IFO."
        )

    manifest["raw_copy"] = {
        "path": str(video_ts_root),
        "method": "dvdbackup-mirror",
        "physical_device": physical_device,
        "status": "complete",
    }

    write_manifest(manifest_path, manifest)

    update_status(
        active_root,
        "RAW COPY COMPLETE: physical disc may now be ejected",
    )

    device = str(video_ts_root)

    update_status(
        active_root,
        "SCANNING: reading titles from local staging",
    )

    scanned = scan_titles(device, scan_log)

    manifest["scan_results"] = scanned
    write_manifest(manifest_path, manifest)

    feature_titles = [
        item
        for item in scanned
        if item["duration_seconds"] >= MIN_MOVIE_SECONDS
    ]

    feature_titles.sort(
        key=lambda item: item["title_number"]
    )

    if len(feature_titles) != expected_items:
        raise RuntimeError(
            f"Expected {expected_items} feature titles, "
            f"but detected {len(feature_titles)}."
        )

    manifest["selected_titles"] = feature_titles
    write_manifest(manifest_path, manifest)

    completed = []

    for index, item in enumerate(feature_titles, start=1):
        title_number = item["title_number"]

        output_file = (
            output_root
            / f"Disc {manifest.get('disc', 1):02d} "
              f"- Feature {index:02d} "
              f"- Title {title_number:02d}.mkv"
        )

        update_status(
            active_root,
            f"RIPPING: feature {index}/{expected_items}, "
            f"DVD title {title_number}",
        )

        run(
            [
                "HandBrakeCLI",
                "-i",
                device,
                "--title",
                str(title_number),
                "-o",
                str(output_file),
                "--format",
                "av_mkv",
                "-e",
                "x264",
                "-q",
                "19",
                "-B",
                "160",
            ],
            log_file=log_file,
            check=True,
        )

        probe = probe_media(output_file)

        if not probe:
            raise RuntimeError(
                f"ffprobe could not read completed file: {output_file}"
            )

        if probe["duration_seconds"] < MIN_MOVIE_SECONDS:
            raise RuntimeError(
                f"Ripped title is too short: {output_file}"
            )

        if probe["size_bytes"] < 300 * 1024 * 1024:
            raise RuntimeError(
                f"Ripped title is unexpectedly small: {output_file}"
            )

        if not probe["has_video"] or not probe["has_audio"]:
            raise RuntimeError(
                f"Ripped title lacks video or audio: {output_file}"
            )

        completed.append(
            {
                "sequence": index,
                "dvd_title": title_number,
                "file": str(output_file),
                "expected_duration_seconds": item["duration_seconds"],
                "duration_seconds": probe["duration_seconds"],
                "size_bytes": probe["size_bytes"],
                "technical_status": "PASS",
            }
        )

        manifest["completed_items"] = completed
        write_manifest(manifest_path, manifest)

        if index < expected_items:
            update_status(
                active_root,
                f"COOLDOWN: waiting {COOLDOWN_SECONDS} seconds "
                "before next feature",
            )
            time.sleep(COOLDOWN_SECONDS)

    manifest["state"] = "validation"
    manifest["workflow"]["rip"] = "complete"
    manifest["workflow"]["cooldown_after_rip"] = "complete"
    manifest["workflow"]["technical_validation"] = "ready"
    write_manifest(manifest_path, manifest)

    update_status(
        active_root,
        "VALIDATION: all expected features ripped and technically readable",
    )

    if validation_root.exists():
        raise RuntimeError(
            f"Validation job already exists: {validation_root}"
        )

    shutil.move(str(active_root), str(validation_root))

    update_status(
        validation_root,
        "READY: waiting for movie-collection metadata and AI validation",
    )

    print("")
    print("=" * 68)
    print(" LOCAL DVD RIP COMPLETE")
    print("=" * 68)
    print(f"Job: {validation_root}")
    print(
        f"Files: "
        f"{Path(manifest['staging_path']) / 'encoded'}"
    )


def main():
    acquire_lock()

    try:
        incoming_job = find_next_job()

        if incoming_job is None:
            print("No ready local DVD jobs.")
            return

        try:
            process_job(incoming_job)
        except Exception as error:
            print(f"FAILED: {error}", file=sys.stderr)

            possible_job_id = incoming_job.name

            for root in (ACTIVE / possible_job_id, incoming_job):
                if not root.exists():
                    continue

                try:
                    manifest_path = root / "job.json"
                    manifest = json.loads(
                        manifest_path.read_text(encoding="utf-8")
                    )
                    manifest["state"] = "failed"
                    manifest.setdefault("errors", []).append(
                        {
                            "time": datetime.now()
                            .astimezone()
                            .isoformat(),
                            "stage": "local_dvd_worker",
                            "message": str(error),
                        }
                    )
                    write_manifest(manifest_path, manifest)
                    update_status(root, f"FAILED: {error}")
                except Exception:
                    pass

                failed_root = FAILED / possible_job_id

                if root != failed_root and not failed_root.exists():
                    shutil.move(str(root), str(failed_root))

                break

            raise SystemExit(1)
    finally:
        release_lock()


if __name__ == "__main__":
    main()
