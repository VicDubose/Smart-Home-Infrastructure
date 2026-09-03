#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

HOME = Path.home()

REMOTE_USER = os.environ.get("CALEB_USER", "caleb")
REMOTE_MEDIA_ROOT = "/srv/media"
LOCAL_MEDIA_ROOT = Path("/mnt/media")

SSH_KEY = HOME / ".ssh/caleb_reverse_sync"
IP_RESOLVER = HOME / "rdp-scripts/Jarvis/media/find_caleb_vpn_ip.sh"

LOG_ROOT = HOME / "Jarvis/logs/reverse-sync"
REPORT_ROOT = HOME / "Jarvis/reports/reverse-sync"
STATE_ROOT = HOME / "Jarvis/state/reverse-sync"

CONFLICT_ROOT = Path("/mnt/appdata/caleb-media/reverse-review")
TEMP_ROOT = Path("/mnt/appdata/caleb-media/reverse-incoming")

REMOTE_MEDIA_LIMIT_BYTES = 250 * 1024**3

VIDEO_EXTENSIONS = {
    ".mkv",
    ".mp4",
    ".m4v",
    ".avi",
    ".mov",
    ".wmv",
    ".ts",
    ".m2ts",
    ".mpg",
    ".mpeg",
    ".webm",
}

ACTIVE_PROCESS_PATTERN = (
    "HandBrakeCLI|ffmpeg|dvdbackup|makemkv|rsync|"
    "jarvis_disc_auto_ingest|jarvis_disc_ingest_guarded|"
    "jarvis_caleb_queue_worker|process_caleb"
)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def run(
    command: list[str],
    *,
    check: bool = True,
    capture: bool = True,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        input=input_text,
        capture_output=capture,
        check=check,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file_handle:
        while True:
            block = file_handle.read(8 * 1024 * 1024)
            if not block:
                break
            digest.update(block)

    return digest.hexdigest()


def ssh_base(host: str) -> list[str]:
    return [
        "ssh",
        "-i",
        str(SSH_KEY),
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ServerAliveInterval=30",
        "-o",
        "ServerAliveCountMax=6",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "LogLevel=ERROR",
        f"{REMOTE_USER}@{host}",
    ]


def resolve_caleb_ip() -> str:
    result = run([str(IP_RESOLVER)])
    host = result.stdout.strip()

    if not host:
        raise RuntimeError("Dynamic Caleb VPN-IP discovery returned no address.")

    return host


def local_media_busy() -> list[str]:
    result = run(
        ["pgrep", "-af", ACTIVE_PROCESS_PATTERN],
        check=False,
    )

    lines = []

    for line in result.stdout.splitlines():
        if "jarvis_reverse_library_sync" in line:
            continue
        if "pgrep -af" in line:
            continue
        lines.append(line)

    return lines


def remote_media_busy(host: str) -> list[str]:
    command = ssh_base(host) + [
        f"pgrep -af '{ACTIVE_PROCESS_PATTERN}' || true"
    ]

    result = run(command, check=False)

    lines = []

    for line in result.stdout.splitlines():
        if "pgrep -af" in line:
            continue
        lines.append(line)

    return lines


def get_remote_manifest(host: str) -> list[dict[str, Any]]:
    remote_program = r'''
import json
import os
from pathlib import Path

root = Path("/srv/media")
extensions = {
    ".mkv", ".mp4", ".m4v", ".avi", ".mov", ".wmv",
    ".ts", ".m2ts", ".mpg", ".mpeg", ".webm"
}

records = []

if root.exists():
    for path in sorted(root.rglob("*")):
        try:
            if not path.is_file():
                continue

            if path.suffix.lower() not in extensions:
                continue

            stat = path.stat()

            records.append({
                "relative_path": str(path.relative_to(root)),
                "absolute_path": str(path),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            })
        except (FileNotFoundError, PermissionError, OSError):
            continue

print(json.dumps(records))
'''

    result = run(
        ssh_base(host) + ["python3", "-"],
        input_text=remote_program,
    )

    return json.loads(result.stdout)


def build_local_indexes() -> tuple[
    dict[str, Path],
    dict[int, list[Path]],
]:
    relative_index: dict[str, Path] = {}
    size_index: dict[int, list[Path]] = defaultdict(list)

    if not LOCAL_MEDIA_ROOT.exists():
        return relative_index, size_index

    for path in LOCAL_MEDIA_ROOT.rglob("*"):
        try:
            if not path.is_file():
                continue

            if path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue

            relative = str(path.relative_to(LOCAL_MEDIA_ROOT))
            size = path.stat().st_size

            relative_index[relative] = path
            size_index[size].append(path)

        except (FileNotFoundError, PermissionError, OSError):
            continue

    return relative_index, size_index


def remote_sha256(host: str, remote_path: str) -> str:
    program = r'''
import hashlib
import sys
from pathlib import Path

path = Path(sys.argv[1])
digest = hashlib.sha256()

with path.open("rb") as file_handle:
    while True:
        block = file_handle.read(8 * 1024 * 1024)
        if not block:
            break
        digest.update(block)

print(digest.hexdigest())
'''

    result = run(
        ssh_base(host) + ["python3", "-", remote_path],
        input_text=program,
    )

    return result.stdout.strip()


def find_hash_duplicate(
    expected_hash: str,
    candidates: list[Path],
    hash_cache: dict[str, str],
) -> Path | None:
    for candidate in candidates:
        cache_key = str(candidate)

        if cache_key not in hash_cache:
            hash_cache[cache_key] = sha256_file(candidate)

        if hash_cache[cache_key] == expected_hash:
            return candidate

    return None


def transfer_file(
    host: str,
    remote_path: str,
    temporary_path: Path,
) -> None:
    temporary_path.parent.mkdir(parents=True, exist_ok=True)

    partial_path = temporary_path.with_name(
        temporary_path.name + ".partial"
    )

    partial_path.unlink(missing_ok=True)

    rsync_ssh = (
        f"ssh -i {SSH_KEY} "
        "-o BatchMode=yes "
        "-o ConnectTimeout=10 "
        "-o ServerAliveInterval=30 "
        "-o ServerAliveCountMax=6 "
        "-o StrictHostKeyChecking=no "
        "-o UserKnownHostsFile=/dev/null "
        "-o LogLevel=ERROR"
    )

    command = [
        "rsync",
        "-a",
        "--protect-args",
        "--partial",
        "--human-readable",
        "--info=progress2",
        "-e",
        rsync_ssh,
        f"{REMOTE_USER}@{host}:{remote_path}",
        str(partial_path),
    ]

    subprocess.run(command, check=True)
    partial_path.replace(temporary_path)


def destination_for_conflict(relative_path: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    relative = Path(relative_path)

    return (
        CONFLICT_ROOT
        / stamp
        / relative.parent
        / relative.name
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pull new Jellyfin media from Caleb into Jarvis."
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compare libraries and produce a report without copying.",
    )

    parser.add_argument(
        "--ignore-busy",
        action="store_true",
        help="Bypass active-process protection. Not recommended.",
    )

    args = parser.parse_args()

    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    STATE_ROOT.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report_path = REPORT_ROOT / f"reverse-sync-{stamp}.json"
    log_path = LOG_ROOT / f"reverse-sync-{stamp}.log"

    report: dict[str, Any] = {
        "started_at": now_iso(),
        "mode": "DRY_RUN" if args.dry_run else "COPY",
        "source": REMOTE_MEDIA_ROOT,
        "destination": str(LOCAL_MEDIA_ROOT),
        "caleb_host": None,
        "remote_files": 0,
        "remote_bytes": 0,
        "copied": [],
        "already_present": [],
        "hash_duplicates": [],
        "conflicts": [],
        "failures": [],
    }

    def log(message: str) -> None:
        line = f"[{now_iso()}] {message}"
        print(line, flush=True)

        with log_path.open("a", encoding="utf-8") as file_handle:
            file_handle.write(line + "\n")

    try:
        if not SSH_KEY.exists():
            raise RuntimeError(f"SSH key does not exist: {SSH_KEY}")

        if not IP_RESOLVER.exists():
            raise RuntimeError(f"IP resolver does not exist: {IP_RESOLVER}")

        log("=" * 72)
        log("JARVIS REVERSE JELLYFIN LIBRARY SYNC")
        log("=" * 72)

        local_busy = local_media_busy()

        if local_busy and not args.ignore_busy:
            raise RuntimeError(
                "Jarvis media pipeline is busy:\n" + "\n".join(local_busy)
            )

        host = resolve_caleb_ip()
        report["caleb_host"] = host

        log(f"Caleb discovered at VPN address {host}")

        remote_busy = remote_media_busy(host)

        if remote_busy and not args.ignore_busy:
            raise RuntimeError(
                "Caleb media pipeline is busy:\n" + "\n".join(remote_busy)
            )

        manifest = get_remote_manifest(host)

        remote_total = sum(int(item["size"]) for item in manifest)

        report["remote_files"] = len(manifest)
        report["remote_bytes"] = remote_total

        log(
            f"Caleb media library: {len(manifest)} files, "
            f"{remote_total / 1024**3:.2f} GiB"
        )

        if remote_total > REMOTE_MEDIA_LIMIT_BYTES:
            raise RuntimeError(
                "Caleb's Jellyfin media library exceeds the "
                "250 GiB storage guard."
            )

        relative_index, size_index = build_local_indexes()

        log(
            f"Jarvis index contains {len(relative_index)} video files."
        )

        local_hash_cache: dict[str, str] = {}

        for number, item in enumerate(manifest, start=1):
            relative_path = item["relative_path"]
            remote_path = item["absolute_path"]
            remote_size = int(item["size"])

            local_target = LOCAL_MEDIA_ROOT / relative_path

            log(
                f"[{number}/{len(manifest)}] Checking {relative_path}"
            )

            existing_exact = relative_index.get(relative_path)

            if existing_exact is not None:
                local_size = existing_exact.stat().st_size

                if local_size == remote_size:
                    report["already_present"].append({
                        "relative_path": relative_path,
                        "reason": "same_path_same_size",
                    })

                    log("SKIP: Same path and size already exist.")
                    continue

                remote_hash = remote_sha256(host, remote_path)
                local_hash = sha256_file(existing_exact)

                if remote_hash == local_hash:
                    report["already_present"].append({
                        "relative_path": relative_path,
                        "reason": "same_path_same_hash",
                    })

                    log("SKIP: Same path and SHA-256 already exist.")
                    continue

                conflict_target = destination_for_conflict(relative_path)

                report["conflicts"].append({
                    "relative_path": relative_path,
                    "existing": str(existing_exact),
                    "review_destination": str(conflict_target),
                    "reason": "same_path_different_content",
                })

                log(
                    "CONFLICT: Existing path has different content. "
                    f"Review destination: {conflict_target}"
                )

                if not args.dry_run:
                    TEMP_ROOT.mkdir(parents=True, exist_ok=True)

                    temporary_file = (
                        TEMP_ROOT / "conflicts" / relative_path
                    )

                    transfer_file(
                        host,
                        remote_path,
                        temporary_file,
                    )

                    copied_hash = sha256_file(temporary_file)

                    if copied_hash != remote_hash:
                        temporary_file.unlink(missing_ok=True)
                        raise RuntimeError(
                            f"Hash verification failed for {relative_path}"
                        )

                    conflict_target.parent.mkdir(
                        parents=True,
                        exist_ok=True,
                    )

                    shutil.move(
                        str(temporary_file),
                        str(conflict_target),
                    )

                continue

            remote_hash = remote_sha256(host, remote_path)

            duplicate = find_hash_duplicate(
                remote_hash,
                size_index.get(remote_size, []),
                local_hash_cache,
            )

            if duplicate is not None:
                report["hash_duplicates"].append({
                    "relative_path": relative_path,
                    "duplicate_of": str(duplicate),
                    "sha256": remote_hash,
                })

                log(
                    "SKIP: Identical content already exists as "
                    f"{duplicate}"
                )
                continue

            if args.dry_run:
                report["copied"].append({
                    "relative_path": relative_path,
                    "size": remote_size,
                    "sha256": remote_hash,
                    "status": "would_copy",
                })

                log("DRY RUN: File would be copied.")
                continue

            temporary_file = TEMP_ROOT / relative_path

            log(f"COPY: {remote_path} -> {local_target}")

            transfer_file(
                host,
                remote_path,
                temporary_file,
            )

            copied_hash = sha256_file(temporary_file)

            if copied_hash != remote_hash:
                temporary_file.unlink(missing_ok=True)

                raise RuntimeError(
                    f"SHA-256 verification failed for {relative_path}"
                )

            local_target.parent.mkdir(parents=True, exist_ok=True)

            if local_target.exists():
                raise RuntimeError(
                    f"Destination appeared during transfer: {local_target}"
                )

            shutil.move(
                str(temporary_file),
                str(local_target),
            )

            relative_index[relative_path] = local_target
            size_index[remote_size].append(local_target)
            local_hash_cache[str(local_target)] = remote_hash

            report["copied"].append({
                "relative_path": relative_path,
                "destination": str(local_target),
                "size": remote_size,
                "sha256": remote_hash,
                "status": "copied_and_verified",
            })

            log("PASS: Copied and SHA-256 verified.")

        report["finished_at"] = now_iso()
        report["result"] = "PASS"

        log("=" * 72)
        log("FINAL SUMMARY")
        log(f"Copied:          {len(report['copied'])}")
        log(f"Already present: {len(report['already_present'])}")
        log(f"Hash duplicates: {len(report['hash_duplicates'])}")
        log(f"Conflicts:       {len(report['conflicts'])}")
        log("Result:          PASS")
        log(f"Report:          {report_path}")
        log("=" * 72)

        report_path.write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )

        return 0

    except Exception as exc:
        report["finished_at"] = now_iso()
        report["result"] = "FAIL"
        report["failures"].append(str(exc))

        log(f"FAIL: {exc}")

        report_path.write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )

        return 1


if __name__ == "__main__":
    sys.exit(main())
