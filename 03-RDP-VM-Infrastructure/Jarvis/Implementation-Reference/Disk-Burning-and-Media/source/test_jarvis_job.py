#!/usr/bin/env python3

from __future__ import annotations

import json

from jarvis_job import normalize_manifest


SAMPLES = {
    "local_dvd": {
        "manifest_version": 1,
        "job_id": "dvd-test-001",
        "created_at": "2026-07-29T07:00:00-05:00",
        "state": "ready",
        "priority": 50,
        "source": "local_dvd",
        "media_type": "movie",
        "profile": "movie",
        "title": "Example DVD",
        "year": 2000,
        "expected_items": 1,
        "ai_model": "llama3:8b",
        "source_metadata": {
            "lane": "local_dvd",
            "device": "/dev/sr0",
            "disc_label": "EXAMPLE",
        },
        "source_path": "/dev/sr0",
        "staging_path": (
            "/mnt/appdata/jarvis-burner-staging/"
            "local-dvd/dvd-test-001"
        ),
        "destination_root": "/mnt/media/Movies",
        "workflow": {},
        "attempts": {},
        "errors": [],
    },
    "local_bluray": {
        "version": 1,
        "job_id": "bluray-test-001",
        "job_type": "local-bluray",
        "media_type": "movie",
        "title": "Example Blu-ray",
        "year": 2001,
        "priority": 100,
        "state": "ready",
        "registered_at": "2026-07-29T07:00:00-05:00",
        "source_path": (
            "/mnt/appdata/jarvis-burner-staging/"
            "local-bluray/bluray-test-001"
        ),
        "media_path": (
            "/mnt/appdata/jarvis-burner-staging/"
            "local-bluray/bluray-test-001/"
            "Example Blu-ray (2001).mkv"
        ),
        "raw_source_path": (
            "/mnt/appdata/arm/media/completed/"
            "unidentified/example.mkv"
        ),
        "raw_source_preserved": True,
    },
    "caleb_remote": {
        "version": 1,
        "job_id": "caleb-test-001",
        "job_type": "caleb-remote",
        "state": "ready",
        "priority": 70,
        "source_path": (
            "/mnt/appdata/caleb-media/incoming/DVD/"
            "EXAMPLE_DISC"
        ),
        "video_ts": (
            "/mnt/appdata/caleb-media/incoming/DVD/"
            "EXAMPLE_DISC/VIDEO_TS"
        ),
        "registered_at": "2026-07-29T07:00:00-05:00",
        "source_preserved": True,
    },
}


def main() -> None:
    for name, sample in SAMPLES.items():
        normalized = normalize_manifest(sample)

        print(f"===== {name} =====")
        print(json.dumps(normalized, indent=2))
        print()

    print("PASS: All current manifest families normalize successfully.")


if __name__ == "__main__":
    main()
