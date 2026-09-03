#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


CURRENT_MANIFEST_VERSION = 1

VALID_SOURCES = {
    "local_dvd",
    "local_bluray",
    "caleb_remote",
    "local_audio_cd",
    "local_data_disc",
    "raw_archive",
}

VALID_MEDIA_TYPES = {
    "movie",
    "tv",
    "music-video",
    "audio",
    "data-disc",
    "raw-archive",
}

VALID_PROFILES = {
    "movie",
    "movie-collection",
    "tv-short",
    "tv-standard",
    "music-video",
    "audio",
    "data-disc",
    "raw-archive",
}


class ManifestError(ValueError):
    """Raised when a Jarvis job manifest cannot be normalized."""


def now_text() -> str:
    return datetime.now().astimezone().isoformat()


def load_json(path: Path | str) -> dict[str, Any]:
    manifest_path = Path(path)

    try:
        data = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
    except FileNotFoundError as exc:
        raise ManifestError(
            f"Manifest does not exist: {manifest_path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ManifestError(
            f"Manifest is not valid JSON: {manifest_path}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ManifestError(
            f"Manifest root must be an object: {manifest_path}"
        )

    return data


def atomic_write(path: Path | str, data: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        text=True,
    )

    temporary_path = Path(temporary_name)

    try:
        with os.fdopen(
            file_descriptor,
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(temporary_path, destination)

    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def source_from_legacy(manifest: dict[str, Any]) -> str:
    source = manifest.get("source")

    if source in VALID_SOURCES:
        return str(source)

    job_type = str(manifest.get("job_type") or "")

    aliases = {
        "local-bluray": "local_bluray",
        "local_bluray": "local_bluray",
        "caleb-remote": "caleb_remote",
        "caleb_remote": "caleb_remote",
        "local-dvd": "local_dvd",
        "local_dvd": "local_dvd",
    }

    if job_type in aliases:
        return aliases[job_type]

    source_metadata = manifest.get("source_metadata")

    if isinstance(source_metadata, dict):
        lane = source_metadata.get("lane")
        if lane in VALID_SOURCES:
            return str(lane)

    raise ManifestError(
        "Unable to determine job source from manifest."
    )


def media_type_from_legacy(
    manifest: dict[str, Any],
    source: str,
) -> str:
    media_type = manifest.get("media_type")

    if media_type in VALID_MEDIA_TYPES:
        return str(media_type)

    if manifest.get("show"):
        return "tv"

    if manifest.get("title"):
        return "movie"

    if source == "local_bluray":
        return "movie"

    if source == "caleb_remote":
        # Existing Caleb registrations are primarily DVD-Video.
        # Without show/movie metadata, classification remains unknown.
        return "tv"

    raise ManifestError(
        "Unable to determine media_type from manifest."
    )


def profile_from_legacy(
    manifest: dict[str, Any],
    media_type: str,
) -> str:
    profile = manifest.get("profile")

    if profile in VALID_PROFILES:
        return str(profile)

    defaults = {
        "movie": "movie",
        "tv": "tv-standard",
        "music-video": "music-video",
        "audio": "audio",
        "data-disc": "data-disc",
        "raw-archive": "raw-archive",
    }

    try:
        return defaults[media_type]
    except KeyError as exc:
        raise ManifestError(
            f"No default profile for media type: {media_type}"
        ) from exc


def destination_from_media_type(media_type: str) -> str:
    destinations = {
        "movie": "/mnt/media/Movies",
        "tv": "/mnt/media/Shows",
        "music-video": "/mnt/media/Music Videos",
        "audio": "/mnt/media/Music",
        "data-disc": "/mnt/media/Archive",
        "raw-archive": "/mnt/media/Archive",
    }

    return destinations[media_type]


def normalize_manifest(
    manifest: dict[str, Any],
) -> dict[str, Any]:
    original = deepcopy(manifest)

    job_id = str(original.get("job_id") or "").strip()

    if not job_id:
        raise ManifestError("Manifest is missing job_id.")

    source = source_from_legacy(original)
    media_type = media_type_from_legacy(original, source)
    profile = profile_from_legacy(original, media_type)

    source_metadata = original.get("source_metadata")

    if not isinstance(source_metadata, dict):
        source_metadata = {}

    source_metadata = deepcopy(source_metadata)
    source_metadata.setdefault("lane", source)

    if source == "local_bluray":
        source_metadata.setdefault("device", "/dev/sr1")
        source_metadata.setdefault("drive_role", "bluray")
        source_metadata.setdefault("intake_method", "arm")

    elif source == "local_dvd":
        source_metadata.setdefault("device", "/dev/sr0")
        source_metadata.setdefault("drive_role", "dvd")
        source_metadata.setdefault("intake_method", "optical")

    elif source == "caleb_remote":
        source_metadata.setdefault(
            "intake_method",
            "ssh_transfer",
        )

    source_path = original.get("source_path")

    if not source_path:
        source_path = (
            original.get("video_ts")
            or original.get("raw_source_path")
            or original.get("media_path")
        )

    if not source_path:
        raise ManifestError("Manifest is missing source_path.")

    staging_path = original.get("staging_path")

    if not staging_path:
        if source == "local_bluray":
            staging_path = original.get("source_path")
        elif source == "caleb_remote":
            staging_path = original.get("source_path")
        else:
            staging_path = str(
                Path(
                    "/mnt/appdata/"
                    "jarvis-burner-staging"
                )
                / source.replace("_", "-")
                / job_id
            )

    workflow_defaults = {
        "intake": "pending",
        "rip": "pending",
        "cooldown_after_rip": "pending",
        "technical_validation": "pending",
        "ai_validation": "pending",
        "library_move": "pending",
        "cleanup": "pending",
    }

    workflow = original.get("workflow")

    if not isinstance(workflow, dict):
        workflow = {}

    workflow = {
        **workflow_defaults,
        **workflow,
    }

    attempts_defaults = {
        "rip": 0,
        "validation": 0,
        "move": 0,
    }

    attempts = original.get("attempts")

    if not isinstance(attempts, dict):
        attempts = {}

    attempts = {
        **attempts_defaults,
        **attempts,
    }

    errors = original.get("errors")

    if not isinstance(errors, list):
        errors = []

    normalized = {
        "manifest_version": CURRENT_MANIFEST_VERSION,
        "job_id": job_id,
        "created_at": (
            original.get("created_at")
            or original.get("registered_at")
            or now_text()
        ),
        "updated_at": original.get("updated_at") or now_text(),
        "state": original.get("state") or "ready",
        "priority": int(original.get("priority", 50)),
        "source": source,
        "media_type": media_type,
        "profile": profile,
        "title": original.get("title"),
        "year": original.get("year"),
        "category": original.get("category"),
        "rating": original.get("rating"),
        "show": original.get("show"),
        "season": original.get("season"),
        "disc": original.get("disc"),
        "episode_start": original.get("episode_start"),
        "expected_items": original.get("expected_items"),
        "ai_model": (
            original.get("ai_model")
            or "llama3:8b"
        ),
        "source_metadata": source_metadata,
        "source_path": str(source_path),
        "raw_source_path": original.get("raw_source_path"),
        "media_path": original.get("media_path"),
        "video_ts": original.get("video_ts"),
        "staging_path": str(staging_path),
        "destination_root": (
            original.get("destination_root")
            or destination_from_media_type(media_type)
        ),
        "workflow": workflow,
        "attempts": attempts,
        "errors": errors,
        "legacy": {
            "version": original.get("version"),
            "job_type": original.get("job_type"),
            "worker": original.get("worker"),
            "raw_source_preserved": original.get(
                "raw_source_preserved"
            ),
            "source_preserved": original.get(
                "source_preserved"
            ),
        },
    }

    validate_manifest(normalized)
    return normalized


def validate_manifest(manifest: dict[str, Any]) -> None:
    required = (
        "manifest_version",
        "job_id",
        "state",
        "source",
        "media_type",
        "profile",
        "source_path",
        "staging_path",
        "destination_root",
        "workflow",
        "attempts",
        "errors",
    )

    missing = [
        key
        for key in required
        if key not in manifest
    ]

    if missing:
        raise ManifestError(
            "Manifest is missing required fields: "
            + ", ".join(missing)
        )

    if manifest["source"] not in VALID_SOURCES:
        raise ManifestError(
            f"Invalid source: {manifest['source']}"
        )

    if manifest["media_type"] not in VALID_MEDIA_TYPES:
        raise ManifestError(
            f"Invalid media_type: {manifest['media_type']}"
        )

    if manifest["profile"] not in VALID_PROFILES:
        raise ManifestError(
            f"Invalid profile: {manifest['profile']}"
        )

    if not isinstance(manifest["workflow"], dict):
        raise ManifestError("workflow must be an object.")

    if not isinstance(manifest["attempts"], dict):
        raise ManifestError("attempts must be an object.")

    if not isinstance(manifest["errors"], list):
        raise ManifestError("errors must be an array.")


def set_state(
    manifest: dict[str, Any],
    state: str,
    *,
    stage: str | None = None,
) -> dict[str, Any]:
    updated = deepcopy(manifest)
    updated["state"] = state
    updated["updated_at"] = now_text()

    if stage is not None:
        updated["stage"] = stage

    validate_manifest(updated)
    return updated


def record_error(
    manifest: dict[str, Any],
    *,
    stage: str,
    code: str,
    message: str,
    retryable: bool,
) -> dict[str, Any]:
    updated = deepcopy(manifest)
    updated.setdefault("errors", []).append(
        {
            "recorded_at": now_text(),
            "stage": stage,
            "code": code,
            "message": message,
            "retryable": retryable,
        }
    )
    updated["state"] = "failed"
    updated["stage"] = stage
    updated["updated_at"] = now_text()

    validate_manifest(updated)
    return updated
