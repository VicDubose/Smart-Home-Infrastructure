#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HOME = Path("/home/onsiteadmin")

ARM_ROOT = Path("/mnt/appdata/arm")
ARM_RAW = ARM_ROOT / "media/raw"
ARM_TRANSCODE = ARM_ROOT / "media/transcode"
ARM_COMPLETED = ARM_ROOT / "media/completed"
ARM_LOGS = ARM_ROOT / "logs"
ARM_MAKEMKV_SETTINGS = ARM_ROOT / "home/.MakeMKV/settings.conf"

JARVIS_ROOT = HOME / "Jarvis"

ARM_HANDOFF_STATE = JARVIS_ROOT / "state/arm-handoff"
ARM_HANDOFF_JOBS = JARVIS_ROOT / "jobs/arm-handoff"
ARM_HANDOFF_QUARANTINE = JARVIS_ROOT / "quarantine/arm-handoff"

CALEB_REPORTS = JARVIS_ROOT / "reports/caleb-auto-ingest"
CALEB_QUARANTINE = JARVIS_ROOT / "quarantine/caleb-auto-ingest"
CALEB_STATE = JARVIS_ROOT / "state/caleb-auto-ingest"

REVERSE_SYNC_REPORTS = JARVIS_ROOT / "reports/reverse-sync"

STATUS_STATE_ROOT = JARVIS_ROOT / "state/status-exporter"
CALEB_HISTORY_FILE = STATUS_STATE_ROOT / "caleb_history.json"


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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_json(path: Path, data: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(data, indent=2, sort_keys=True))
        temporary.replace(path)
    except OSError:
        pass


def latest_file(root: Path, pattern: str) -> Path | None:
    if not root.exists():
        return None

    files = [path for path in root.glob(pattern) if path.is_file()]
    if not files:
        return None

    return max(files, key=lambda path: path.stat().st_mtime)


def latest_recursive_file(root: Path, filename: str) -> Path | None:
    if not root.exists():
        return None

    files = [path for path in root.rglob(filename) if path.is_file()]
    if not files:
        return None

    return max(files, key=lambda path: path.stat().st_mtime)


def iso_mtime(path: Path | None) -> str | None:
    if path is None:
        return None

    try:
        return datetime.fromtimestamp(
            path.stat().st_mtime,
            tz=timezone.utc,
        ).isoformat()
    except OSError:
        return None


def count_files(root: Path, suffix: str = ".mkv") -> int:
    if not root.exists():
        return 0

    try:
        return sum(
            1
            for path in root.rglob("*")
            if path.is_file() and path.name.lower().endswith(suffix.lower())
        )
    except OSError:
        return 0


def bytes_for(root: Path) -> int:
    if not root.exists():
        return 0

    output = run(["du", "-sb", "--", str(root)], timeout=60)

    try:
        return int(output.split()[0])
    except (IndexError, ValueError):
        return 0


def human_bytes(value: int) -> str:
    size = float(value)

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024

    return f"{size:.1f} TB"


def newest_child_name(roots: list[Path]) -> str | None:
    candidates: list[Path] = []

    for root in roots:
        if not root.exists():
            continue

        try:
            candidates.extend(path for path in root.iterdir() if path.is_dir())
        except OSError:
            continue

    if not candidates:
        return None

    newest = max(candidates, key=lambda path: path.stat().st_mtime)
    return newest.name


def docker_arm_processes() -> str:
    return run(
        [
            "docker",
            "exec",
            "arm",
            "bash",
            "-lc",
            (
                "pgrep -af "
                "'[/]opt/arm/arm/ripper/main\\.py|"
                "[H]andBrakeCLI|"
                "[m]akemkvcon|"
                "[d]vdbackup|"
                "[f]fmpeg'"
            ),
        ],
        timeout=6,
    )


def detect_arm_stage(processes: str) -> str:
    lower = processes.lower()

    if "handbrakecli" in lower or "ffmpeg" in lower:
        return "transcoding"

    if "makemkvcon" in lower or "dvdbackup" in lower:
        return "ripping"

    if "/opt/arm/arm/ripper/main.py" in lower:
        return "processing"

    if count_files(ARM_COMPLETED):
        return "completed_waiting"

    return "idle"


def makemkv_key_status() -> str:
    settings = ""

    try:
        settings = ARM_MAKEMKV_SETTINGS.read_text(errors="ignore")
    except OSError:
        pass

    if re.search(r'app_Key\s*=\s*"[^"]+"', settings):
        return "configured"

    logs = latest_file(ARM_LOGS, "*.log")
    if logs:
        try:
            text = logs.read_text(errors="ignore")[-20000
sudo sed -i \
  '/from pathlib import Path/a from jarvis_status_extensions import build_extensions' \
  /opt/jarvis-status/jarvis_status_exporter.py
sudo python3 - <<'PY'
from pathlib import Path

path = Path("/opt/jarvis-status/jarvis_status_exporter.py")
text = path.read_text()

old = """def build_status():
    disk = shutil.disk_usage('/')
    jellyfin = docker_state('jellyfin')
    public = jellyfin_public()
    vpn = vpn_hosts()

    return {
"""

new = """def build_status():
    disk = shutil.disk_usage('/')
    jellyfin = docker_state('jellyfin')
    public = jellyfin_public()
    vpn = vpn_hosts()

    payload = {
"""

if old not in text:
    raise SystemExit(
        "Could not find the expected build_status opening block."
    )

text = text.replace(old, new, 1)

old_end = """        'pipeline': pipeline_status(),
    }
"""

new_end = """        'pipeline': pipeline_status(),
    }

    payload.update(
        build_extensions(
            caleb_online=vpn['caleb_online'],
            caleb_ip=vpn['caleb_ip'],
        )
    )

    return payload
"""

if old_end not in text:
    raise SystemExit(
        "Could not find the expected build_status closing block."
    )

text = text.replace(old_end, new_end, 1)
path.write_text(text)
