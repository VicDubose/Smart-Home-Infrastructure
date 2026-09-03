#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import sqlite3
import subprocess
import threading
import time
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


BIND_HOST = os.environ.get("JARVIS_STATUS_HOST", "192.168.50.51")
BIND_PORT = int(os.environ.get("JARVIS_STATUS_PORT", "8765"))

HOME = Path("/home/onsiteadmin")
JARVIS_ROOT = HOME / "Jarvis"

CALEB_INCOMING_ROOT = Path("/mnt/appdata/caleb-media/incoming/DVD")
CALEB_STATE_ROOT = JARVIS_ROOT / "state/caleb-auto-ingest"
CALEB_REPORT_ROOT = JARVIS_ROOT / "reports/caleb-auto-ingest"
CALEB_QUARANTINE_ROOT = JARVIS_ROOT / "quarantine/caleb-auto-ingest"
CALEB_JOB_ROOT = JARVIS_ROOT / "jobs/caleb-auto-ingest"

ARM_ROOT = Path("/mnt/appdata/arm")
ARM_RAW_ROOT = ARM_ROOT / "media/raw"
ARM_TRANSCODE_ROOT = ARM_ROOT / "media/transcode"
ARM_COMPLETED_ROOT = ARM_ROOT / "media/completed"
ARM_LOG_ROOT = ARM_ROOT / "logs"
ARM_DB = ARM_ROOT / "home/db/arm.db"
ARM_MAKEMKV_SETTINGS = ARM_ROOT / "home/.MakeMKV/settings.conf"

ARM_HANDOFF_STATE = JARVIS_ROOT / "state/arm-handoff"
ARM_HANDOFF_REPORTS = JARVIS_ROOT / "reports/arm-handoff"
ARM_HANDOFF_JOBS = JARVIS_ROOT / "jobs/arm-handoff"
ARM_HANDOFF_QUARANTINE = JARVIS_ROOT / "quarantine/arm-handoff"

REVERSE_SYNC_REPORTS = JARVIS_ROOT / "reports/reverse-sync"
REVERSE_SYNC_READINESS = REVERSE_SYNC_REPORTS / "reverse-sync-readiness-20260719-011416.txt"

MEDIA_ROOT = Path("/mnt/media")
SHOWS_ROOT = MEDIA_ROOT / "Shows"

SHARED_LOCK = Path("/run/user/1000/jarvis-media-ingest.lock")

ARM_FAILED_HOLD_ROOT = ARM_ROOT / "media/failed-hold"
MOTD_PATH = Path("/run/motd.dynamic")

VIDEO_SUFFIXES = (".mkv", ".mp4", ".m4v", ".avi")

STAGING_ROOTS = {
    "arm_raw": ARM_RAW_ROOT,
    "arm_transcode": ARM_TRANSCODE_ROOT,
    "arm_completed": ARM_COMPLETED_ROOT,
    "arm_failed_hold": ARM_FAILED_HOLD_ROOT,
    "jarvis_bluray": Path("/mnt/appdata/jarvis-burner-staging/local-bluray"),
    "jarvis_dvd": Path("/mnt/appdata/jarvis-burner-staging/local-dvd"),
    "jarvis_dvd_raw": Path("/mnt/appdata/jarvis-burner-staging/local-dvd-raw"),
    "caleb_remote": Path("/mnt/appdata/jarvis-burner-staging/caleb-remote"),
    "validation_active": Path("/mnt/appdata/jarvis-validation-staging/active"),
    "validation_review": Path("/mnt/appdata/jarvis-validation-staging/review"),
    "validation_blocked": Path("/mnt/appdata/jarvis-validation-staging/blocked"),
    "validation_rerip": Path("/mnt/appdata/jarvis-validation-staging/rerip"),
    "validation_finished": Path("/mnt/appdata/jarvis-validation-staging/finished"),
    "emergency_hold": Path("/mnt/media/.jarvis-emergency-hold"),
}

VPN_RANGE = "10.8.0.0/24"
VPN_ROUTER_IP = "10.8.0.1"

CACHE_SECONDS = 20
CACHE: dict[str, Any] = {"at": 0.0, "data": None}
CACHE_LOCK = threading.Lock()


def run(args: list[str], timeout: int = 10) -> str:
    try:
        result = subprocess.run(
            args,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
        return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def bash(command: str, timeout: int = 10) -> str:
    return run(["bash", "-lc", command], timeout=timeout)


def utc_iso(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()


def file_modified(path: Path) -> str | None:
    try:
        return utc_iso(path.stat().st_mtime)
    except OSError:
        return None


def latest_file(root: Path, pattern: str = "*") -> Path | None:
    if not root.exists():
        return None

    files = [path for path in root.glob(pattern) if path.is_file()]
    if not files:
        return None

    return max(files, key=lambda path: path.stat().st_mtime)


def latest_recursive_file(root: Path, pattern: str = "*") -> Path | None:
    if not root.exists():
        return None

    files = [path for path in root.rglob(pattern) if path.is_file()]
    if not files:
        return None

    return max(files, key=lambda path: path.stat().st_mtime)


def load_json(path: Path | None, default: Any = None) -> Any:
    if path is None or not path.exists():
        return default

    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def bytes_for(path: Path) -> int:
    if not path.exists():
        return 0

    output = run(["du", "-sb", "--", str(path)], timeout=60)

    try:
        return int(output.split()[0])
    except (IndexError, ValueError):
        return 0


def human_bytes(value: int | float | None) -> str:
    if value is None:
        return "unknown"

    size = float(value)

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024

    return f"{size:.1f} TB"


def count_files(root: Path, suffixes: tuple[str, ...] | None = None) -> int:
    if not root.exists():
        return 0

    count = 0

    try:
        for path in root.rglob("*"):
            if not path.is_file():
                continue

            if suffixes is None or path.suffix.lower() in suffixes:
                count += 1
    except OSError:
        pass

    return count


def count_directories(root: Path) -> int:
    if not root.exists():
        return 0

    try:
        return sum(1 for path in root.iterdir() if path.is_dir())
    except OSError:
        return 0



def newest_file_epoch(root: Path) -> float | None:
    if not root.exists():
        return None

    newest: float | None = None

    try:
        for item in root.rglob("*"):
            if not item.is_file():
                continue

            modified = item.stat().st_mtime

            if newest is None or modified > newest:
                newest = modified
    except OSError:
        pass

    return newest


def staging_root_status(root: Path) -> dict[str, Any]:
    root_bytes = bytes_for(root)
    newest = newest_file_epoch(root)

    return {
        "path": str(root),
        "exists": root.exists(),
        "bytes": root_bytes,
        "size": human_bytes(root_bytes),
        "files": count_files(root),
        "videos": count_files(root, VIDEO_SUFFIXES),
        "jobs": count_directories(root),
        "modified": utc_iso(newest),
    }


def arm_raw_job_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    if not ARM_RAW_ROOT.exists():
        return rows

    processing = bool(
        run(
            [
                "pgrep",
                "-af",
                "[m]akemkvcon|[H]andBrakeCLI|[d]vdbackup|[f]fmpeg",
            ],
            timeout=5,
        )
    )

    now = time.time()

    try:
        folders = sorted(
            (
                item
                for item in ARM_RAW_ROOT.iterdir()
                if item.is_dir()
            ),
            key=lambda item: item.name.lower(),
        )
    except OSError:
        return rows

    for folder in folders:
        files = count_files(folder)
        videos = count_files(folder, VIDEO_SUFFIXES)
        folder_bytes = bytes_for(folder)
        newest = newest_file_epoch(folder)

        age_hours = (
            round((now - newest) / 3600, 1)
            if newest is not None
            else None
        )

        if files == 0:
            state = "empty_orphan"
        elif processing and age_hours is not None and age_hours < 0.25:
            state = "active"
        else:
            state = "stranded_review"

        rows.append(
            {
                "name": folder.name,
                "path": str(folder),
                "state": state,
                "bytes": folder_bytes,
                "size": human_bytes(folder_bytes),
                "files": files,
                "videos": videos,
                "age_hours": age_hours,
                "modified": utc_iso(newest),
            }
        )

    return rows


def failed_hold_job_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    if not ARM_FAILED_HOLD_ROOT.exists():
        return rows

    try:
        folders = sorted(
            (
                item
                for item in ARM_FAILED_HOLD_ROOT.iterdir()
                if item.is_dir()
            ),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return rows

    for folder in folders[:20]:
        marker = folder / ".jarvis-failed-hold.json"
        metadata = load_json(marker, {})

        if not isinstance(metadata, dict):
            metadata = {}

        folder_bytes = bytes_for(folder)

        rows.append(
            {
                "name": folder.name,
                "path": str(folder),
                "bytes": folder_bytes,
                "size": human_bytes(folder_bytes),
                "files": count_files(folder),
                "videos": count_files(folder, VIDEO_SUFFIXES),
                "modified": file_modified(folder),
                "purge_after": (
                    metadata.get("purge_after")
                    or metadata.get("purge_after_utc")
                ),
                "reason": metadata.get("reason"),
                "marker": str(marker) if marker.exists() else None,
            }
        )

    return rows


def staging_status() -> dict[str, Any]:
    roots = {
        name: staging_root_status(root)
        for name, root in STAGING_ROOTS.items()
    }

    working_names = [
        name
        for name in roots
        if name != "emergency_hold"
    ]

    return {
        "roots": roots,
        "working_bytes": sum(
            roots[name]["bytes"]
            for name in working_names
        ),
        "working_size": human_bytes(
            sum(
                roots[name]["bytes"]
                for name in working_names
            )
        ),
        "total_bytes": sum(
            item["bytes"]
            for item in roots.values()
        ),
        "total_size": human_bytes(
            sum(
                item["bytes"]
                for item in roots.values()
            )
        ),
        "total_files": sum(
            item["files"]
            for item in roots.values()
        ),
        "total_videos": sum(
            item["videos"]
            for item in roots.values()
        ),
        "total_jobs": sum(
            item["jobs"]
            for item in roots.values()
        ),
        "arm_raw_jobs": arm_raw_job_rows(),
        "failed_hold_jobs": failed_hold_job_rows(),
    }


def motd_status() -> dict[str, Any]:
    try:
        text = MOTD_PATH.read_text(errors="ignore")
    except OSError:
        text = ""

    def number(pattern: str) -> int:
        match = re.search(pattern, text, re.IGNORECASE)
        return int(match.group(1)) if match else 0

    return {
        "restart_required": (
            Path("/var/run/reboot-required").exists()
            or "system restart required" in text.lower()
        ),
        "updates_available": number(
            r"(\d+)\s+updates can be applied immediately"
        ),
        "standard_security_updates": number(
            r"(\d+)\s+of these updates are standard security updates"
        ),
        "esm_security_updates": number(
            r"(\d+)\s+additional security updates can be applied"
        ),
        "firmware_upgrades": number(
            r"(\d+)\s+devices?\s+ha(?:s|ve)\s+a firmware upgrade available"
        ),
        "source": str(MOTD_PATH),
        "modified": file_modified(MOTD_PATH),
    }


def latest_library_media() -> dict[str, Any] | None:
    if not SHOWS_ROOT.exists():
        return None

    newest: Path | None = None
    newest_epoch: float | None = None

    try:
        for item in SHOWS_ROOT.rglob("*"):
            if (
                not item.is_file()
                or item.suffix.lower() not in VIDEO_SUFFIXES
            ):
                continue

            modified = item.stat().st_mtime

            if newest_epoch is None or modified > newest_epoch:
                newest = item
                newest_epoch = modified
    except OSError:
        return None

    if newest is None:
        return None

    try:
        size = newest.stat().st_size
    except OSError:
        size = 0

    return {
        "name": newest.name,
        "path": str(newest),
        "bytes": size,
        "size": human_bytes(size),
        "modified": utc_iso(newest_epoch),
    }


def docker_state(name: str) -> dict[str, Any]:
    raw = run(
        ["docker", "inspect", name, "--format", "{{json .State}}"],
        timeout=5,
    )

    if not raw:
        return {
            "installed": False,
            "running": False,
            "status": "missing",
            "health": "missing",
        }

    try:
        state = json.loads(raw)
    except json.JSONDecodeError:
        return {
            "installed": True,
            "running": False,
            "status": "unknown",
            "health": "unknown",
        }

    health = (state.get("Health") or {}).get("Status")

    return {
        "installed": True,
        "running": bool(state.get("Running")),
        "status": state.get("Status", "unknown"),
        "health": health or ("running" if state.get("Running") else "stopped"),
        "started_at": state.get("StartedAt"),
        "finished_at": state.get("FinishedAt"),
        "exit_code": state.get("ExitCode"),
    }


def systemd_user_state(unit: str) -> dict[str, Any]:
    active = run(
        ["systemctl", "--user", "is-active", unit],
        timeout=5,
    ) or "unknown"

    enabled = run(
        ["systemctl", "--user", "is-enabled", unit],
        timeout=5,
    ) or "unknown"

    show = run(
        [
            "systemctl",
            "--user",
            "show",
            unit,
            "--property=SubState,ActiveEnterTimestamp,InactiveEnterTimestamp,Result",
            "--value",
        ],
        timeout=5,
    )

    values = show.splitlines()

    return {
        "active": active,
        "enabled": enabled,
        "sub_state": values[0] if len(values) > 0 else None,
        "active_enter": values[1] if len(values) > 1 else None,
        "inactive_enter": values[2] if len(values) > 2 else None,
        "result": values[3] if len(values) > 3 else None,
    }


def process_lines(pattern: str) -> list[str]:
    output = run(["pgrep", "-af", pattern], timeout=5)
    return output.splitlines()[:12] if output else []


def jellyfin_public() -> dict[str, Any]:
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:8096/System/Info/Public",
            timeout=3,
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return {}


def memory_percent() -> float | None:
    values: dict[str, int] = {}

    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            values[key] = int(value.strip().split()[0])

        total = values["MemTotal"]
        available = values["MemAvailable"]

        return round((total - available) * 100 / total, 1)
    except Exception:
        return None


def uptime_seconds() -> int | None:
    try:
        return int(float(Path("/proc/uptime").read_text().split()[0]))
    except Exception:
        return None


def maximum_temperature() -> float | None:
    raw = run(["sensors", "-j"], timeout=5)

    if not raw:
        return None

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None

    temperatures: list[float] = []

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key, value in item.items():
                if (
                    isinstance(value, (int, float))
                    and key.lower().endswith("_input")
                    and "temp" in key.lower()
                    and 0 < float(value) < 110
                ):
                    temperatures.append(float(value))
                else:
                    walk(value)

        elif isinstance(item, list):
            for value in item:
                walk(value)

    walk(data)

    return round(max(temperatures), 1) if temperatures else None


def storage_status(path: Path) -> dict[str, Any]:
    try:
        usage = shutil.disk_usage(path)

        percent = round(usage.used * 100 / usage.total, 1)

        return {
            "path": str(path),
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "percent": percent,
            "free": human_bytes(usage.free),
            "used": human_bytes(usage.used),
            "total": human_bytes(usage.total),
        }
    except OSError:
        return {
            "path": str(path),
            "percent": None,
            "free": "unavailable",
            "used": "unavailable",
            "total": "unavailable",
        }


def open_ports(ip: str) -> list[int]:
    ports = (22, 3389, 8096, 8123)
    found: list[int] = []

    for port in ports:
        try:
            with socket.create_connection((ip, port), timeout=0.3):
                found.append(port)
        except OSError:
            pass

    return found


def vpn_hosts() -> dict[str, Any]:
    output = run(
        ["nmap", "-n", "-sn", "-oG", "-", VPN_RANGE],
        timeout=15,
    )

    hosts: list[str] = []

    for line in output.splitlines():
        match = re.search(
            r"Host:\s+(\d+\.\d+\.\d+\.\d+).*Status:\s+Up",
            line,
        )

        if match:
            ip = match.group(1)

            if ip != VPN_ROUTER_IP:
                hosts.append(ip)

    candidates = []

    for ip in hosts:
        ports = open_ports(ip)

        candidates.append(
            {
                "ip": ip,
                "open_ports": ports,
                "score": len(ports),
            }
        )

    likely = [item for item in candidates if item["score"] >= 3]
    likely.sort(key=lambda item: (-item["score"], item["ip"]))

    selected = likely[0]["ip"] if likely else None

    return {
        "active_hosts": len(hosts),
        "hosts": hosts,
        "candidates": candidates,
        "caleb_ip": selected,
        "caleb_online": selected is not None,
        "detection": "service_fingerprint_22_3389_8096_8123",
    }


def normalize_job_name(name: str) -> str:
    name = name.removesuffix(".receiving")
    name = re.sub(r"_\d{8}_\d{6}$", "", name)
    name = re.sub(r"[_\s]+", " ", name)
    return name.strip()


def current_caleb_queue() -> dict[str, Any]:
    jobs: list[Path] = []

    if CALEB_INCOMING_ROOT.exists():
        try:
            jobs = [
                path
                for path in CALEB_INCOMING_ROOT.iterdir()
                if path.is_dir()
            ]
        except OSError:
            jobs = []

    jobs.sort(key=lambda path: path.stat().st_mtime, reverse=True)

    receiving = [
        path for path in jobs if path.name.endswith(".receiving")
    ]

    completed = [
        path for path in jobs if not path.name.endswith(".receiving")
    ]

    latest = jobs[0] if jobs else None
    current = receiving[0] if receiving else latest

    normalized = [
        normalize_job_name(path.name).lower()
        for path in jobs
    ]

    duplicates = {
        name: count
        for name, count in Counter(normalized).items()
        if count > 1
    }

    recent_jobs = []

    for path in jobs[:12]:
        recent_jobs.append(
            {
                "name": normalize_job_name(path.name),
                "folder": path.name,
                "state": (
                    "receiving"
                    if path.name.endswith(".receiving")
                    else "received"
                ),
                "modified": file_modified(path),
                "size": human_bytes(bytes_for(path)),
            }
        )

    video_ts_count = int(
        bash(
            "find "
            + repr(str(CALEB_INCOMING_ROOT))
            + " -type d -name VIDEO_TS 2>/dev/null | wc -l",
            timeout=30,
        )
        or 0
    )

    bdmv_count = int(
        bash(
            "find "
            + repr(str(CALEB_INCOMING_ROOT))
            + " -type d -name BDMV 2>/dev/null | wc -l",
            timeout=30,
        )
        or 0
    )

    return {
        "path": str(CALEB_INCOMING_ROOT),
        "exists": CALEB_INCOMING_ROOT.exists(),
        "current_job": (
            normalize_job_name(current.name)
            if current
            else None
        ),
        "current_folder": current.name if current else None,
        "incoming_jobs": len(jobs),
        "received_jobs": len(completed),
        "receiving_jobs": len(receiving),
        "video_ts_jobs": video_ts_count,
        "bdmv_jobs": bdmv_count,
        "queue_bytes": bytes_for(CALEB_INCOMING_ROOT),
        "queue_size": human_bytes(bytes_for(CALEB_INCOMING_ROOT)),
        "duplicate_group_count": len(duplicates),
        "duplicate_groups": duplicates,
        "recent_jobs": recent_jobs,
    }


def arm_database_status() -> dict[str, Any]:
    if not ARM_DB.exists():
        return {
            "available": False,
            "latest_job": None,
            "tables": [],
        }

    try:
        connection = sqlite3.connect(f"file:{ARM_DB}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row

        tables = [
            row["name"]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type='table'
                ORDER BY name
                """
            )
        ]

        latest_job = None

        for table in ("job", "jobs"):
            if table not in tables:
                continue

            try:
                row = connection.execute(
                    f"SELECT * FROM {table} ORDER BY id DESC LIMIT 1"
                ).fetchone()

                if row:
                    latest_job = {
                        key: row[key]
                        for key in row.keys()
                        if key not in {
                            "apikey",
                            "api_key",
                            "password",
                            "token",
                        }
                    }
                    break
            except sqlite3.Error:
                continue

        connection.close()

        return {
            "available": True,
            "latest_job": latest_job,
            "tables": tables,
        }

    except sqlite3.Error as error:
        return {
            "available": False,
            "latest_job": None,
            "error": str(error),
            "tables": [],
        }


def arm_status() -> dict[str, Any]:
    container = docker_state("arm")

    processes = process_lines(
        r"/opt/arm/arm/ripper/main\.py|HandBrakeCLI|makemkvcon"
    )

    process_text = "\n".join(processes).lower()

    if "handbrakecli" in process_text:
        stage = "transcoding"
    elif "makemkvcon" in process_text:
        stage = "ripping"
    elif "/opt/arm/arm/ripper/main.py" in process_text:
        stage = "identifying"
    else:
        stage = "idle"

    completed_jobs = []

    completed_tv = ARM_COMPLETED_ROOT / "tv"

    if completed_tv.exists():
        try:
            folders = [
                path
                for path in completed_tv.iterdir()
                if path.is_dir()
            ]

            folders.sort(
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )

            for path in folders[:8]:
                completed_jobs.append(
                    {
                        "name": path.name,
                        "modified": file_modified(path),
                        "files": count_files(
                            path,
                            (".mkv", ".mp4", ".avi", ".m4v"),
                        ),
                        "size": human_bytes(bytes_for(path)),
                    }
                )
        except OSError:
            pass

    key_present = False

    if ARM_MAKEMKV_SETTINGS.exists():
        try:
            key_present = "app_Key" in ARM_MAKEMKV_SETTINGS.read_text()
        except OSError:
            pass

    raw_bytes = bytes_for(ARM_RAW_ROOT)
    transcode_bytes = bytes_for(ARM_TRANSCODE_ROOT)
    completed_bytes = bytes_for(ARM_COMPLETED_ROOT)

    return {
        "container": container,
        "online": container.get("running", False),
        "healthy": container.get("health") == "healthy",
        "web_port": 8181,
        "stage": stage,
        "active": bool(processes),
        "active_processes": processes,
        "database": arm_database_status(),
        "raw": {
            "path": str(ARM_RAW_ROOT),
            "files": count_files(
                ARM_RAW_ROOT,
                (".mkv", ".mp4", ".avi", ".m4v"),
            ),
            "bytes": raw_bytes,
            "size": human_bytes(raw_bytes),
        },
        "transcode": {
            "path": str(ARM_TRANSCODE_ROOT),
            "files": count_files(
                ARM_TRANSCODE_ROOT,
                (".mkv", ".mp4", ".avi", ".m4v"),
            ),
            "bytes": transcode_bytes,
            "size": human_bytes(transcode_bytes),
        },
        "completed": {
            "path": str(ARM_COMPLETED_ROOT),
            "files": count_files(
                ARM_COMPLETED_ROOT,
                (".mkv", ".mp4", ".avi", ".m4v"),
            ),
            "bytes": completed_bytes,
            "size": human_bytes(completed_bytes),
            "jobs": completed_jobs,
        },
        "makemkv": {
            "key_present": key_present,
            "settings_modified": file_modified(
                ARM_MAKEMKV_SETTINGS
            ),
        },
        "handoff_timer": systemd_user_state(
            "jarvis-arm-handoff.timer"
        ),
        "handoff_service": systemd_user_state(
            "jarvis-arm-handoff.service"
        ),
    }


def latest_handoff_state() -> dict[str, Any] | None:
    path = latest_file(ARM_HANDOFF_STATE, "*.json")
    data = load_json(path)

    if not isinstance(data, dict):
        return None

    return {
        **data,
        "state_file": str(path),
        "state_file_modified": file_modified(path),
    }


def latest_caleb_summary() -> dict[str, Any] | None:
    path = latest_file(
        CALEB_REPORT_ROOT,
        "run-summary-*.json",
    )

    data = load_json(path)

    if not isinstance(data, dict):
        return None

    return {
        **data,
        "report_file": str(path),
        "report_modified": file_modified(path),
    }


def latest_reverse_sync() -> dict[str, Any] | None:
    path = latest_file(
        REVERSE_SYNC_REPORTS,
        "reverse-sync-*.json",
    )

    data = load_json(path)

    if not isinstance(data, dict):
        return None

    return {
        **data,
        "report_file": str(path),
        "report_modified": file_modified(path),
    }


def latest_failure(root: Path) -> dict[str, Any] | None:
    path = latest_recursive_file(root, "*.json")

    if path is None:
        return None

    data = load_json(path, {})

    if not isinstance(data, dict):
        data = {}

    return {
        "file": str(path),
        "modified": file_modified(path),
        "show": data.get("show"),
        "season": data.get("season"),
        "disc": data.get("disc"),
        "reason": data.get("reason"),
        "status": data.get("status") or data.get("final_result"),
        "source": data.get("source") or data.get("raw_folder"),
    }


def count_json(root: Path) -> int:
    if not root.exists():
        return 0

    try:
        return sum(1 for _ in root.rglob("*.json"))
    except OSError:
        return 0


def shared_pipeline_status(
    arm: dict[str, Any],
    caleb_queue: dict[str, Any],
) -> dict[str, Any]:
    arm_processes = arm.get("active_processes") or []

    caleb_processes = process_lines(
        r"jarvis_caleb_queue_worker|jarvis_disc_ingest_guarded_v2"
    )

    handoff_processes = process_lines(
        r"jarvis_arm_handoff_worker"
    )

    ffmpeg_processes = process_lines(r"ffmpeg|ffprobe")

    if arm_processes:
        stage = f"arm_{arm.get('stage', 'working')}"
        source = "arm_local"
        job = (
            (
                arm.get("database", {})
                .get("latest_job")
                or {}
            ).get("title")
            or (
                arm.get("completed", {})
                .get("jobs", [{}])[0]
                .get("name")
                if arm.get("completed", {}).get("jobs")
                else None
            )
            or "ARM local disc"
        )

    elif caleb_processes:
        text = "\n".join(caleb_processes).lower()

        if "handbrake" in text:
            stage = "caleb_encoding"
        elif "validate" in text:
            stage = "caleb_validating"
        else:
            stage = "caleb_processing"

        source = "caleb_remote"
        job = caleb_queue.get("current_job")

    elif handoff_processes:
        stage = "arm_handoff"
        source = "arm_local"
        job = (
            (
                latest_handoff_state()
                or {}
            ).get("show")
            or "ARM completed media"
        )

    elif caleb_queue.get("receiving_jobs", 0) > 0:
        stage = "vpn_receiving"
        source = "caleb_remote"
        job = caleb_queue.get("current_job")

    elif caleb_queue.get("incoming_jobs", 0) > 0:
        stage = "queue_waiting"
        source = "caleb_remote"
        job = caleb_queue.get("current_job")

    elif arm.get("completed", {}).get("files", 0) > 0:
        stage = "arm_completed"
        source = "arm_local"
        job = (
            arm.get("completed", {})
            .get("jobs", [{}])[0]
            .get("name")
            if arm.get("completed", {}).get("jobs")
            else None
        )

    else:
        stage = "idle"
        source = "none"
        job = None

    lock_busy = bool(
        run(
            [
                "flock",
                "-n",
                str(SHARED_LOCK),
                "-c",
                "true",
            ],
            timeout=2,
        )
    )

    # flock produces no output on success, so verify through fuser instead.
    lock_holders = run(
        ["fuser", str(SHARED_LOCK)],
        timeout=3,
    )

    return {
        "stage": stage,
        "source": source,
        "job": job,
        "busy": bool(
            arm_processes
            or caleb_processes
            or handoff_processes
            or ffmpeg_processes
        ),
        "shared_lock": str(SHARED_LOCK),
        "shared_lock_busy": bool(lock_holders),
        "lock_holders": lock_holders.split(),
        "arm_processes": arm_processes,
        "caleb_processes": caleb_processes,
        "handoff_processes": handoff_processes,
        "media_processes": ffmpeg_processes,
        "caleb_timer": systemd_user_state(
            "jarvis-caleb-auto-ingest.timer"
        ),
        "caleb_service": systemd_user_state(
            "jarvis-caleb-auto-ingest.service"
        ),
        "arm_handoff_timer": systemd_user_state(
            "jarvis-arm-handoff.timer"
        ),
        "arm_handoff_service": systemd_user_state(
            "jarvis-arm-handoff.service"
        ),
    }


def build_status() -> dict[str, Any]:
    jellyfin_container = docker_state("jellyfin")
    jellyfin_info = jellyfin_public()

    vpn = vpn_hosts()
    caleb_queue = current_caleb_queue()
    arm = arm_status()

    media_storage = storage_status(MEDIA_ROOT)
    root_storage = storage_status(Path("/"))
    appdata_storage = storage_status(Path("/mnt/appdata"))

    arm_latest_state = latest_handoff_state()
    caleb_summary = latest_caleb_summary()
    reverse_sync = latest_reverse_sync()

    pipeline = shared_pipeline_status(arm, caleb_queue)
    staging = staging_status()
    system_alerts = motd_status()
    latest_media = latest_library_media()

    caleb_last_known = {
        "online": vpn.get("caleb_online"),
        "vpn_ip": vpn.get("caleb_ip"),
        "identification": vpn.get("detection"),
        "last_system_check": file_modified(
            REVERSE_SYNC_READINESS
        ),
        "last_library_sync": (
            reverse_sync.get("finished_at")
            if reverse_sync
            else None
        ),
        "last_library_sync_result": (
            reverse_sync.get("result")
            if reverse_sync
            else None
        ),
        "last_library_sync_mode": (
            reverse_sync.get("mode")
            if reverse_sync
            else None
        ),
        "last_jellyfin_storage_percent": (
            caleb_summary.get("storage_percent")
            if caleb_summary
            else None
        ),
        "last_jellyfin_storage_free": (
            human_bytes(
                caleb_summary.get("storage_free_bytes")
            )
            if caleb_summary
            else None
        ),
        "queue": caleb_queue,
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": "1.1",
        "exporter": {
            "name": "jarvis_status_exporter",
            "source": str(Path(__file__).resolve()),
            "source_modified": file_modified(Path(__file__)),
            "cache_seconds": CACHE_SECONDS,
        },
        "system_alerts": system_alerts,

        "skynet": {
            "online": True,
            "hostname": socket.gethostname(),
            "lan_ip": "192.168.50.51",
            "load_1m": round(os.getloadavg()[0], 2),
            "memory_percent": memory_percent(),
            "temperature_c": maximum_temperature(),
            "uptime_seconds": uptime_seconds(),
            "root_storage": root_storage,
            "appdata_storage": appdata_storage,
        },

        "containers": {
            "jellyfin": jellyfin_container,
            "arm": arm.get("container"),
            "open_webui": docker_state("open-webui"),
            "eufy_ws": docker_state("eufy_ws"),
        },

        "jellyfin": {
            "online": jellyfin_container.get("running", False),
            "healthy": jellyfin_container.get("health") == "healthy",
            "server_name": jellyfin_info.get("ServerName"),
            "version": jellyfin_info.get("Version"),
            "product_name": jellyfin_info.get("ProductName"),
            "storage": media_storage,
            "latest_media": latest_media,
        },

        "vpn": vpn,

        "caleb": caleb_last_known,

        "arm": arm,

        "pipeline": pipeline,

        "staging": staging,

        "queues": {
            "caleb": caleb_queue,
            "arm_raw": arm.get("raw"),
            "arm_transcode": arm.get("transcode"),
            "arm_completed": arm.get("completed"),
        },

        "failures": {
            "caleb_count": count_json(
                CALEB_QUARANTINE_ROOT
            ),
            "caleb_latest": latest_failure(
                CALEB_QUARANTINE_ROOT
            ),
            "arm_count": count_json(
                ARM_HANDOFF_QUARANTINE
            ),
            "arm_latest": latest_failure(
                ARM_HANDOFF_QUARANTINE
            ),
            "total": (
                count_json(CALEB_QUARANTINE_ROOT)
                + count_json(ARM_HANDOFF_QUARANTINE)
            ),
        },

        "successes": {
            "arm_latest": arm_latest_state,
            "caleb_latest_summary": caleb_summary,
            "reverse_sync_latest": reverse_sync,
        },
    }


def cached_status() -> dict[str, Any]:
    now = time.time()

    with CACHE_LOCK:
        if (
            CACHE["data"] is None
            or now - CACHE["at"] >= CACHE_SECONDS
        ):
            CACHE["data"] = build_status()
            CACHE["at"] = now

        return CACHE["data"]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        route = self.path.split("?", 1)[0].rstrip("/")

        if route not in ("", "/status"):
            self.send_error(404)
            return

        payload = json.dumps(
            cached_status(),
            indent=2,
            default=str,
        ).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header(
            "Cache-Control",
            f"max-age={CACHE_SECONDS}",
        )
        self.send_header(
            "Access-Control-Allow-Origin",
            "*",
        )
        self.send_header(
            "Content-Length",
            str(len(payload)),
        )
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format_string: str, *args: Any) -> None:
        print(
            f"{self.client_address[0]} - "
            f"{format_string % args}",
            flush=True,
        )


if __name__ == "__main__":
    server = ThreadingHTTPServer(
        (BIND_HOST, BIND_PORT),
        Handler,
    )

    print(
        "Jarvis status exporter listening on "
        f"http://{BIND_HOST}:{BIND_PORT}/status",
        flush=True,
    )

    server.serve_forever()
