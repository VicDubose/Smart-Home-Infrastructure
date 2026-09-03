#!/usr/bin/env python3
"""
Jarvis ARM completed-media handoff worker.

Safety model:
ARM completed output
    -> explicit profile lookup
    -> stable-file check
    -> collision check
    -> job staging copy
    -> SHA-256 verification
    -> full FFmpeg decode
    -> Jarvis technical + AI validation
    -> sacred move gate
    -> library audit
    -> persistent state record

ARM raw and completed source files are never deleted.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HOME = Path.home()

ARM_COMPLETED_TV = Path("/mnt/appdata/arm/media/completed/tv")
MEDIA_ROOT = Path("/mnt/media")
DEFAULT_LIBRARY_ROOT = Path("/mnt/media/Shows")

PROFILE_FILE = HOME / "Jarvis/config/arm_handoff_profiles.json"
STATE_ROOT = HOME / "Jarvis/state/arm-handoff"
JOB_ROOT = HOME / "Jarvis/jobs/arm-handoff"
QUARANTINE_ROOT = HOME / "Jarvis/quarantine/arm-handoff"
GLOBAL_REPORT_ROOT = HOME / "Jarvis/reports/arm-handoff"

VALIDATOR = HOME / "rdp-scripts/Jarvis/media/jarvis_validate_rip.py"
MOVE_GATE = HOME / "rdp-scripts/Jarvis/media/jarvis_move_if_valid.py"
AUDITOR = HOME / "rdp-scripts/Jarvis/media/jarvis_library_audit.py"

FOLDER_PATTERN = re.compile(
    r"^(?P<show>.+?)\s+S(?P<season>\d{1,2})D(?P<disc>\d{1,2})"
    r"(?:\s+\([^)]*\))?$",
    re.IGNORECASE,
)

ACTIVE_PROCESS_PATTERN = (
    r"[/]opt/arm/arm/ripper/main\.py|"
    r"[H]andBrakeCLI|"
    r"[m]akemkvcon|"
    r"[d]vdbackup|"
    r"[f]fmpeg"
)


class HandoffBlocked(RuntimeError):
    """Expected safety block requiring review."""


@dataclass(frozen=True)
class DiscIdentity:
    show_from_folder: str
    season: int
    disc: int

    @property
    def key(self) -> str:
        return (
            f"{normalize_name(self.show_from_folder)}|"
            f"{self.season}|{self.disc}"
        )


@dataclass(frozen=True)
class DiscProfile:
    show: str
    season: int
    disc: int
    start_episode: int
    end_episode: int
    minimum_runtime_minutes: int
    maximum_runtime_minutes: int
    ai_model: str
    minimum_source_age_seconds: int
    library_root: Path

    @property
    def expected_count(self) -> int:
        return self.end_episode - self.start_episode + 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def log(message: str = "") -> None:
    print(message, flush=True)


def normalize_name(value: str) -> str:
    value = value.casefold()
    value = value.replace("’", "'")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return value or "unknown"


def natural_key(path: Path) -> list[Any]:
    return [
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\d+)", path.name)
    ]


def run(
    command: list[str],
    *,
    check: bool = True,
    capture: bool = False,
    stdout_file: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    log("$ " + " ".join(repr(part) for part in command))

    if stdout_file is not None:
        stdout_file.parent.mkdir(parents=True, exist_ok=True)
        with stdout_file.open("a", encoding="utf-8") as handle:
            result = subprocess.run(
                command,
                text=True,
                stdout=handle,
                stderr=subprocess.STDOUT,
                check=False,
            )
    else:
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            check=False,
        )

    if check and result.returncode != 0:
        detail = ""
        if capture:
            detail = (result.stderr or result.stdout or "").strip()
        raise HandoffBlocked(
            f"Command failed with status {result.returncode}: "
            f"{' '.join(command)}"
            + (f"\n{detail}" if detail else "")
        )

    return result


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HandoffBlocked(f"Required JSON file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise HandoffBlocked(f"Invalid JSON in {path}: {exc}") from exc


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def ensure_required_paths() -> None:
    if not MEDIA_ROOT.is_mount():
        raise HandoffBlocked("/mnt/media is not currently a mount point.")

    if not ARM_COMPLETED_TV.is_dir():
        raise HandoffBlocked(
            f"ARM completed-TV directory is missing: {ARM_COMPLETED_TV}"
        )

    for script in (VALIDATOR, MOVE_GATE, AUDITOR):
        if not script.is_file():
            raise HandoffBlocked(f"Required Jarvis script is missing: {script}")

    for directory in (
        STATE_ROOT,
        JOB_ROOT,
        QUARANTINE_ROOT,
        GLOBAL_REPORT_ROOT,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def arm_is_idle() -> bool:
    container = run(
        [
            "docker",
            "inspect",
            "arm",
            "--format",
            "{{.State.Status}} "
            "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
        ],
        capture=True,
    )

    status = container.stdout.strip()
    log(f"ARM container: {status}")

    if not status.startswith("running "):
        log(
            f"ARM container is stopped ({status}); "
            "treating stopped ARM as idle for completed-media handoff."
        )
        return True

    processes = run(
        [
            "docker",
            "exec",
            "arm",
            "bash",
            "-lc",
            f"pgrep -af '{ACTIVE_PROCESS_PATTERN}'",
        ],
        check=False,
        capture=True,
    )

    if processes.returncode == 0 and processes.stdout.strip():
        log("ARM activity detected:")
        log(processes.stdout.strip())
        return False

    return True


def load_profiles() -> tuple[dict[str, Any], dict[str, Any]]:
    document = load_json(PROFILE_FILE)

    if not isinstance(document, dict):
        raise HandoffBlocked("ARM profile document must be a JSON object.")

    defaults = document.get("defaults", {})
    profiles = document.get("tv_discs", {})

    if not isinstance(defaults, dict) or not isinstance(profiles, dict):
        raise HandoffBlocked(
            "ARM profile document requires object fields "
            "'defaults' and 'tv_discs'."
        )

    return defaults, profiles


def parse_identity(folder: Path) -> DiscIdentity | None:
    match = FOLDER_PATTERN.match(folder.name.strip())
    if not match:
        return None

    return DiscIdentity(
        show_from_folder=match.group("show").strip(),
        season=int(match.group("season")),
        disc=int(match.group("disc")),
    )


def build_profile(
    identity: DiscIdentity,
    defaults: dict[str, Any],
    profile_data: dict[str, Any],
) -> DiscProfile:
    if profile_data.get("enabled", True) is not True:
        raise HandoffBlocked(f"Profile is disabled: {identity.key}")

    show = str(profile_data.get("show", "")).strip()
    if not show:
        raise HandoffBlocked(f"Profile has no show name: {identity.key}")

    season = int(profile_data.get("season", identity.season))
    disc = int(profile_data.get("disc", identity.disc))
    start_episode = int(profile_data["start_episode"])
    end_episode = int(profile_data["end_episode"])

    if season != identity.season or disc != identity.disc:
        raise HandoffBlocked(
            f"Profile identity does not match source folder: {identity.key}"
        )

    if start_episode < 1 or end_episode < start_episode:
        raise HandoffBlocked(
            f"Invalid episode range in profile: {identity.key}"
        )

    return DiscProfile(
        show=show,
        season=season,
        disc=disc,
        start_episode=start_episode,
        end_episode=end_episode,
        minimum_runtime_minutes=int(
            profile_data.get("minimum_runtime_minutes", 18)
        ),
        maximum_runtime_minutes=int(
            profile_data.get("maximum_runtime_minutes", 60)
        ),
        ai_model=str(
            profile_data.get(
                "ai_model",
                defaults.get("ai_model", "llama3:8b"),
            )
        ),
        minimum_source_age_seconds=int(
            profile_data.get(
                "minimum_source_age_seconds",
                defaults.get("minimum_source_age_seconds", 600),
            )
        ),
        library_root=Path(
            profile_data.get(
                "library_root",
                defaults.get("library_root", str(DEFAULT_LIBRARY_ROOT)),
            )
        ),
    )


def source_files(folder: Path) -> list[Path]:
    return sorted(
        [
            item
            for item in folder.iterdir()
            if item.is_file() and item.suffix.casefold() == ".mkv"
        ],
        key=natural_key,
    )


def files_are_stable(files: list[Path], minimum_age: int) -> tuple[bool, int]:
    if not files:
        return False, 0

    newest_mtime = max(path.stat().st_mtime for path in files)
    age = max(0, int(time.time() - newest_mtime))
    return age >= minimum_age, age


def state_key(source: Path, profile: DiscProfile) -> str:
    raw = (
        f"{source.resolve()}|{profile.show}|{profile.season}|"
        f"{profile.disc}|{profile.start_episode}|{profile.end_episode}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def state_path(source: Path, profile: DiscProfile) -> Path:
    return STATE_ROOT / f"{state_key(source, profile)}.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe_file(path: Path) -> dict[str, Any]:
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            (
                "format=duration,size,format_name:"
                "stream=index,codec_type,codec_name,width,height,channels"
            ),
            "-of",
            "json",
            str(path),
        ],
        capture=True,
    )

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise HandoffBlocked(
            f"ffprobe returned invalid JSON for {path.name}: {exc}"
        ) from exc


def find_value(document: Any, key: str) -> Any:
    if isinstance(document, dict):
        if key in document:
            return document[key]
        for value in document.values():
            found = find_value(value, key)
            if found is not None:
                return found
    elif isinstance(document, list):
        for value in document:
            found = find_value(value, key)
            if found is not None:
                return found
    return None


def collision_state(
    destination: Path,
    expected_names: list[str],
) -> str:
    exists = [(destination / name).exists() for name in expected_names]

    if all(exists):
        return "all"
    if any(exists):
        return "partial"
    return "none"


def process_source(
    source: Path,
    identity: DiscIdentity,
    profile: DiscProfile,
) -> str:
    state_file = state_path(source, profile)

    if state_file.exists():
        existing_state = load_json(state_file)
        log(
            f"SKIP: Already recorded as "
            f"{existing_state.get('status', 'processed')}: {source.name}"
        )
        return "skipped"

    files = source_files(source)

    if len(files) != profile.expected_count:
        raise HandoffBlocked(
            f"{source.name}: expected {profile.expected_count} MKV files "
            f"for S{profile.season:02d}E{profile.start_episode:02d}-"
            f"S{profile.season:02d}E{profile.end_episode:02d}, "
            f"but found {len(files)}."
        )

    stable, age = files_are_stable(
        files,
        profile.minimum_source_age_seconds,
    )
    if not stable:
        log(
            f"WAIT: {source.name} newest file is only {age} seconds old; "
            f"requires {profile.minimum_source_age_seconds} seconds."
        )
        return "waiting"

    destination = (
        profile.library_root
        / profile.show
        / f"Season {profile.season:02d}"
    )

    episode_numbers = list(
        range(profile.start_episode, profile.end_episode + 1)
    )
    expected_names = [
        f"{profile.show} - "
        f"S{profile.season:02d}E{episode:02d}.mkv"
        for episode in episode_numbers
    ]

    collision = collision_state(destination, expected_names)

    if collision == "partial":
        existing = [
            name for name in expected_names if (destination / name).exists()
        ]
        raise HandoffBlocked(
            f"{source.name}: partial destination collision. Existing: "
            + ", ".join(existing)
        )

    if collision == "all":
        record = {
            "schema_version": 1,
            "status": "ALREADY_IMPORTED",
            "recorded_at": utc_now(),
            "source": str(source),
            "profile_key": identity.key,
            "show": profile.show,
            "season": profile.season,
            "disc": profile.disc,
            "episodes": expected_names,
            "destination": str(destination),
            "source_preserved": True,
        }
        write_json(state_file, record)
        log(
            f"SKIP: All destination episodes already exist for {source.name}."
        )
        return "already_imported"

    job_id = (
        f"{slugify(profile.show)}-S{profile.season:02d}-"
        f"D{profile.disc:02d}-{timestamp()}"
    )
    job = JOB_ROOT / job_id
    staging = job / "staging"
    reports = job / "reports"
    quarantine = QUARANTINE_ROOT / job_id

    staging.mkdir(parents=True, exist_ok=False)
    reports.mkdir(parents=True, exist_ok=True)
    quarantine.mkdir(parents=True, exist_ok=True)

    validation_file = reports / "validation_result.json"
    decode_report = reports / "full_decode_report.txt"
    handoff_manifest = reports / "handoff_manifest.json"

    mappings: list[dict[str, Any]] = []

    log("===== COPY INTO JOB STAGING =====")

    for source_file, episode, destination_name in zip(
        files,
        episode_numbers,
        expected_names,
        strict=True,
    ):
        staged_file = staging / destination_name

        log(f"{source_file.name} -> {destination_name}")
        shutil.copy2(source_file, staged_file)

        source_hash = sha256_file(source_file)
        staged_hash = sha256_file(staged_file)

        if source_hash != staged_hash:
            raise HandoffBlocked(
                f"Copy-integrity failure for {source_file.name}"
            )

        probe = probe_file(staged_file)

        mappings.append(
            {
                "source": str(source_file),
                "staged": str(staged_file),
                "episode": episode,
                "source_sha256": source_hash,
                "staged_sha256": staged_hash,
                "bytes": staged_file.stat().st_size,
                "probe": probe,
            }
        )

    write_json(
        handoff_manifest,
        {
            "schema_version": 1,
            "created_at": utc_now(),
            "job_id": job_id,
            "profile_key": identity.key,
            "source": str(source),
            "destination": str(destination),
            "show": profile.show,
            "season": profile.season,
            "disc": profile.disc,
            "start_episode": profile.start_episode,
            "end_episode": profile.end_episode,
            "ai_model": profile.ai_model,
            "source_preservation": {
                "delete_raw": False,
                "delete_completed": False,
            },
            "files": mappings,
        },
    )

    log("===== FULL DECODE VALIDATION =====")

    for mapping in mappings:
        staged_file = Path(mapping["staged"])
        log(f"Decoding {staged_file.name}")

        result = run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-xerror",
                "-i",
                str(staged_file),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-f",
                "null",
                "-",
            ],
            check=False,
            capture=True,
        )

        with decode_report.open("a", encoding="utf-8") as handle:
            handle.write(f"FILE: {staged_file}\n")
            handle.write(f"RETURN_CODE: {result.returncode}\n")
            if result.stdout:
                handle.write(result.stdout)
            if result.stderr:
                handle.write(result.stderr)
            handle.write("\n")

        if result.returncode != 0:
            raise HandoffBlocked(
                f"Full decode failed for {staged_file.name}. "
                f"See {decode_report}"
            )

    log("===== JARVIS TECHNICAL + AI VALIDATION =====")

    run(
        [
            sys.executable,
            str(VALIDATOR),
            "--show",
            profile.show,
            "--season",
            str(profile.season),
            "--start",
            str(profile.start_episode),
            "--end",
            str(profile.end_episode),
            "--staging",
            str(staging),
            "--write-result",
            str(validation_file),
            "--ai",
            profile.ai_model,
            "--min-runtime",
            str(profile.minimum_runtime_minutes),
            "--max-runtime",
            str(profile.maximum_runtime_minutes),
        ]
    )

    validation = load_json(validation_file)
    final_result = str(
        find_value(validation, "final_result")
        or find_value(validation, "final_validation")
        or ""
    ).upper()

    if final_result != "PASS":
        raise HandoffBlocked(
            f"Jarvis final validation was {final_result or 'UNKNOWN'}. "
            f"Files remain in {staging}"
        )

    log("===== SACRED MOVE GATE =====")

    destination.mkdir(parents=True, exist_ok=True)

    run(
        [
            sys.executable,
            str(MOVE_GATE),
            "--validation",
            str(validation_file),
            "--destination",
            str(destination),
        ]
    )

    missing_after_move = [
        name for name in expected_names if not (destination / name).is_file()
    ]
    if missing_after_move:
        raise HandoffBlocked(
            "Move gate returned success, but destination files are missing: "
            + ", ".join(missing_after_move)
        )

    log("===== LIBRARY AUDIT =====")

    run(
        [
            sys.executable,
            str(AUDITOR),
            "--show",
            profile.show,
            "--library",
            str(profile.library_root),
        ],
        check=False,
        stdout_file=reports / "library_audit.txt",
    )

    state_record = {
        "schema_version": 1,
        "status": "PASS",
        "completed_at": utc_now(),
        "job_id": job_id,
        "job": str(job),
        "profile_key": identity.key,
        "source": str(source),
        "source_preserved": True,
        "show": profile.show,
        "season": profile.season,
        "disc": profile.disc,
        "start_episode": profile.start_episode,
        "end_episode": profile.end_episode,
        "destination": str(destination),
        "validation": str(validation_file),
        "handoff_manifest": str(handoff_manifest),
        "decode_report": str(decode_report),
        "episodes": expected_names,
    }
    write_json(state_file, state_record)

    log(
        f"PASS: Imported {profile.show} "
        f"S{profile.season:02d}E{profile.start_episode:02d}-"
        f"S{profile.season:02d}E{profile.end_episode:02d}"
    )
    log(f"State: {state_file}")
    log("ARM raw and completed source files remain preserved.")

    return "passed"


def write_block_report(source: Path | None, reason: str) -> Path:
    GLOBAL_REPORT_ROOT.mkdir(parents=True, exist_ok=True)

    report = GLOBAL_REPORT_ROOT / (
        f"blocked-{timestamp()}-{slugify(source.name if source else 'worker')}.json"
    )

    write_json(
        report,
        {
            "schema_version": 1,
            "status": "BLOCK",
            "recorded_at": utc_now(),
            "source": str(source) if source else None,
            "reason": reason,
            "source_preserved": True,
        },
    )

    return report


def main() -> int:
    log("=" * 72)
    log("JARVIS ARM HANDOFF WORKER")
    log("=" * 72)

    try:
        ensure_required_paths()

        if not arm_is_idle():
            log("WAIT: ARM is active. Handoff scan deferred.")
            return 0

        defaults, profile_document = load_profiles()

        folders = sorted(
            [
                folder
                for folder in ARM_COMPLETED_TV.iterdir()
                if folder.is_dir()
            ],
            key=natural_key,
        )

        if not folders:
            log("No ARM completed TV folders found.")
            return 0

        counters = {
            "passed": 0,
            "skipped": 0,
            "already_imported": 0,
            "waiting": 0,
            "unknown": 0,
            "blocked": 0,
        }

        for source in folders:
            log()
            log("-" * 72)
            log(f"Source: {source}")

            identity = parse_identity(source)

            if identity is None:
                reason = (
                    "Folder name does not match the required "
                    "'Show Name SxxDxx (optional year)' pattern."
                )
                report = write_block_report(source, reason)
                log(f"REVIEW: {reason}")
                log(f"Report: {report}")
                counters["unknown"] += 1
                continue

            profile_data = profile_document.get(identity.key)

            if not isinstance(profile_data, dict):
                reason = (
                    f"No explicit ARM handoff profile exists for "
                    f"{identity.key}"
                )
                report = write_block_report(source, reason)
                log(f"REVIEW: {reason}")
                log(f"Report: {report}")
                counters["unknown"] += 1
                continue

            try:
                profile = build_profile(
                    identity,
                    defaults,
                    profile_data,
                )
                result = process_source(source, identity, profile)
                counters[result] = counters.get(result, 0) + 1
            except HandoffBlocked as exc:
                report = write_block_report(source, str(exc))
                log(f"BLOCK: {exc}")
                log(f"Report: {report}")
                counters["blocked"] += 1
            except Exception as exc:  # Defensive quarantine boundary.
                report = write_block_report(
                    source,
                    f"Unexpected {type(exc).__name__}: {exc}",
                )
                log(f"BLOCK: Unexpected {type(exc).__name__}: {exc}")
                log(f"Report: {report}")
                counters["blocked"] += 1

        log()
        log("=" * 72)
        log("FINAL ARM HANDOFF SUMMARY")
        log("=" * 72)
        for name, value in counters.items():
            log(f"{name.replace('_', ' ').title()}: {value}")

        # Safety blocks are reported but do not make the recurring timer fail.
        return 0

    except HandoffBlocked as exc:
        report = write_block_report(None, str(exc))
        log(f"BLOCK: {exc}")
        log(f"Report: {report}")
        return 1
    except Exception as exc:
        report = write_block_report(
            None,
            f"Unexpected {type(exc).__name__}: {exc}",
        )
        log(f"FATAL: {type(exc).__name__}: {exc}")
        log(f"Report: {report}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
