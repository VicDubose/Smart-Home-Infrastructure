#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

HOME = Path.home()
ARM_MEDIA = Path("/mnt/appdata/arm/media")
COMPLETED = ARM_MEDIA / "completed"
STAGE_ROOT = ARM_MEDIA / "personal-staging"
REPORT_ROOT = HOME / "Jarvis/reports/personal-movies"
STATE_FILE = HOME / "Jarvis/state/personal-movie-router.json"
MOVIE_LIBRARY = Path("/mnt/media/Movies/General/Unrated")
VIDEO_EXTS = {".mkv", ".mp4", ".m4v"}
MODEL_DEFAULT = "llama3:8b"
MIN_MOVIE_SECONDS = 45 * 60
MIN_MOVIE_BYTES = 300 * 1024 * 1024


def now_stamp() -> str:
    return datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def safe_name(value: str) -> str:
    value = re.sub(r"[^\w .()'-]+", "-", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip(" .-")
    return value or "Unknown Movie"


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


GENERIC_TITLES = {
    "unknown",
    "unknownmovie",
    "nolabel",
    "untitled",
    "dvdvideo",
    "video",
    "title",
    "movie",
}

MUSIC_COLLECTION_MARKERS = (
    "concert",
    "music video",
    "video collection",
    "greatest hits",
    "karaoke",
    "live at",
    "live in",
)


def run(cmd: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def arm_active() -> tuple[bool, str]:
    proc = run([
        "docker", "exec", "arm", "bash", "-lc",
        r"pgrep -af '[/]opt/arm/arm/ripper/main\.py|[H]andBrakeCLI|[m]akemkvcon|[d]vdbackup|[f]fmpeg' || true",
    ], timeout=20)
    details = proc.stdout.strip()
    return bool(details), details


def ensure_dirs() -> None:
    for path in (
        REPORT_ROOT,
        STATE_FILE.parent,
        STAGE_ROOT / "rerip",
        STAGE_ROOT / "review",
        STAGE_ROOT / "block",
        MOVIE_LIBRARY,
    ):
        path.mkdir(parents=True, exist_ok=True)


def video_files(folder: Path) -> list[Path]:
    return sorted(
        [
            path for path in folder.rglob("*")
            if path.is_file() and path.suffix.casefold() in VIDEO_EXTS
        ],
        key=lambda p: p.name.casefold(),
    )


def looks_like_tv(path: Path) -> bool:
    text = " ".join(path.parts[-3:])
    return (
        any(part.casefold() in {"tv", "shows", "show", "series"} for part in path.parts)
        or bool(re.search(r"\bS\d{1,2}\s*D\d{1,2}\b", text, re.I))
        or bool(re.search(r"\bS\d{1,2}E\d{1,3}\b", text, re.I))
    )


def parse_title_year(folder: Path) -> tuple[str, int | None]:
    name = folder.name.strip()
    name = re.sub(r"\s+(?:disc|disk)\s*\d+\s*$", "", name, flags=re.I)
    match = re.match(r"^(.*?)\s*\((\d{4})\)\s*$", name)
    if match:
        return safe_name(match.group(1)), int(match.group(2))
    match = re.match(r"^(.*?)\s+(\d{4})\s*$", name)
    if match:
        return safe_name(match.group(1)), int(match.group(2))
    return safe_name(name), None


def host_to_container(path: Path) -> str:
    resolved = path.resolve()
    root = ARM_MEDIA.resolve()
    try:
        rel = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path is outside ARM media root: {path}") from exc
    return str(Path("/home/arm/media") / rel)


def probe(path: Path) -> dict[str, Any]:
    fields = (
        "format=filename,duration,size,format_name:"
        "stream=index,codec_type,codec_name,width,height,channels"
    )
    host_ffprobe = shutil.which("ffprobe")
    if host_ffprobe:
        cmd = [
            host_ffprobe, "-v", "error",
            "-show_entries", fields,
            "-of", "json", str(path),
        ]
    else:
        cmd = [
            "docker", "exec", "arm", "ffprobe", "-v", "error",
            "-show_entries", fields,
            "-of", "json", host_to_container(path),
        ]
    proc = run(cmd, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"ffprobe failed for {path}")
    data = json.loads(proc.stdout)
    fmt = data.get("format", {})
    streams = data.get("streams", [])
    return {
        "path": str(path),
        "size_bytes": int(float(fmt.get("size") or path.stat().st_size)),
        "duration_seconds": float(fmt.get("duration") or 0),
        "format_name": fmt.get("format_name"),
        "has_video": any(s.get("codec_type") == "video" for s in streams),
        "has_audio": any(s.get("codec_type") == "audio" for s in streams),
        "streams": streams,
    }


def decode_check(path: Path) -> tuple[bool, str]:
    host_ffmpeg = shutil.which("ffmpeg")
    if host_ffmpeg:
        cmd = [
            host_ffmpeg, "-hide_banner", "-v", "error", "-xerror",
            "-i", str(path), "-map", "0:v:0", "-f", "null", "-",
        ]
    else:
        cmd = [
            "docker", "exec", "arm", "ffmpeg",
            "-hide_banner", "-v", "error", "-xerror",
            "-i", host_to_container(path),
            "-map", "0:v:0", "-f", "null", "-",
        ]
    proc = run(cmd, timeout=6 * 60 * 60)
    text = (proc.stderr or proc.stdout).strip()
    return proc.returncode == 0, text[-4000:]


def fingerprint(folder: Path, files: list[Path]) -> str:
    digest = hashlib.sha256()
    digest.update(str(folder.resolve()).encode())
    for path in files:
        stat = path.stat()
        digest.update(str(path.resolve()).encode())
        digest.update(str(stat.st_size).encode())
        digest.update(str(stat.st_mtime_ns).encode())
    return digest.hexdigest()


def load_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"schema_version": 1, "jobs": {}}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError
        data.setdefault("schema_version", 1)
        data.setdefault("jobs", {})
        return data
    except (OSError, ValueError, json.JSONDecodeError):
        return {"schema_version": 1, "jobs": {}}


def save_state(state: dict[str, Any]) -> None:
    temp = STATE_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temp, STATE_FILE)


def stage_bundle(status: str, job_name: str, files: list[Path], report: dict[str, Any]) -> Path:
    bucket = {
        "RERIP": "rerip",
        "REVIEW": "review",
        "BLOCK": "block",
    }.get(status.upper(), "review")
    bundle = STAGE_ROOT / bucket / f"{safe_name(job_name).replace(' ', '-')}-{now_stamp()}"
    media = bundle / "media"
    media.mkdir(parents=True, exist_ok=False)

    used: set[str] = set()
    for index, source in enumerate(files, start=1):
        name = source.name
        if name in used:
            name = f"{index:02d}-{name}"
        used.add(name)
        target = media / name
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)

    report = dict(report)
    report["staging_path"] = str(bundle)
    (bundle / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (bundle / "report.txt").write_text(
        f"Status: {status}\n"
        f"Job: {job_name}\n"
        f"Reason: {report.get('reason', 'Unspecified')}\n"
        f"Source preserved: YES\n"
        f"Jellyfin import: NO\n",
        encoding="utf-8",
    )
    return bundle


def ai_review(model: str, evidence: dict[str, Any]) -> dict[str, Any]:
    prompt = (
        "You are Jarvis, a conservative media-ingest reviewer. "
        "Return one JSON object only with keys decision, reason, confidence. "
        "decision must be PASS, REVIEW, BLOCK, or RERIP. "
        "PASS only when the evidence clearly describes one complete feature-length movie, "
        "with valid audio/video, a successful full decode, and no ambiguous competing title. "
        "Never override a technical failure.\n\nEvidence:\n"
        + json.dumps(evidence, indent=2, sort_keys=True)
    )
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }).encode("utf-8")
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            outer = json.loads(response.read().decode("utf-8"))
        inner = json.loads(outer.get("response", "{}"))
        decision = str(inner.get("decision", "REVIEW")).upper()
        if decision not in {"PASS", "REVIEW", "BLOCK", "RERIP"}:
            decision = "REVIEW"
        return {
            "decision": decision,
            "reason": str(inner.get("reason", "AI returned no reason.")),
            "confidence": inner.get("confidence"),
        }
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError) as exc:
        return {
            "decision": "REVIEW",
            "reason": f"AI review unavailable or invalid: {exc}",
            "confidence": 0,
        }


def destination_for(title: str, year: int | None, suffix: str) -> tuple[Path, Path]:
    display = f"{title} ({year})" if year else title
    folder = MOVIE_LIBRARY / display
    target = folder / f"{display}{suffix.lower()}"
    return folder, target


def atomic_copy_and_verify(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(f".{target.name}.partial-{os.getpid()}")
    try:
        with source.open("rb") as src, partial.open("xb") as dst:
            shutil.copyfileobj(src, dst, length=16 * 1024 * 1024)
            dst.flush()
            os.fsync(dst.fileno())
        source_stat = source.stat()
        if partial.stat().st_size != source_stat.st_size:
            raise RuntimeError("Copied size does not match source.")
        copied_probe = probe(partial)
        if not copied_probe["has_video"] or not copied_probe["has_audio"]:
            raise RuntimeError("Copied file failed stream verification.")
        if copied_probe["duration_seconds"] < MIN_MOVIE_SECONDS:
            raise RuntimeError("Copied movie is below minimum duration.")
        os.replace(partial, target)
    finally:
        if partial.exists():
            partial.unlink()


def write_report(report: dict[str, Any]) -> Path:
    path = REPORT_ROOT / f"{safe_name(report['job']).replace(' ', '-')}-{now_stamp()}.json"
    report["report_path"] = str(path)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return path


def refresh_jellyfin() -> dict[str, Any]:
    key_file = HOME / "Jarvis/config/jellyfin_api_key"
    if not key_file.exists():
        return {"requested": False, "reason": "No Jellyfin API key file configured."}
    key = key_file.read_text(encoding="utf-8").strip()
    if not key:
        return {"requested": False, "reason": "Jellyfin API key file is empty."}
    url = f"http://127.0.0.1:8096/Library/Refresh?api_key={key}"
    request = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return {"requested": True, "http_status": response.status}
    except (OSError, urllib.error.URLError) as exc:
        return {"requested": False, "reason": str(exc)}


def process_folder(
    folder: Path,
    model: str,
    commit: bool,
    force: bool,
    state: dict[str, Any],
) -> dict[str, Any]:
    files = video_files(folder)
    title, year = parse_title_year(folder)
    job_name = f"{title} ({year})" if year else title
    job_id = hashlib.sha256(str(folder.resolve()).encode()).hexdigest()
    fp = fingerprint(folder, files)

    prior = state["jobs"].get(job_id)
    if prior and prior.get("fingerprint") == fp and not force:
        return {
            "status": "SKIP",
            "job": job_name,
            "reason": f"Unchanged job already recorded as {prior.get('status')}.",
            "source": str(folder),
        }

    probes: list[dict[str, Any]] = []
    probe_errors: list[str] = []
    for path in files:
        try:
            probes.append(probe(path))
        except Exception as exc:
            probe_errors.append(f"{path}: {exc}")

    movie_candidates = [
        item for item in probes
        if item["has_video"]
        and item["has_audio"]
        and item["duration_seconds"] >= MIN_MOVIE_SECONDS
        and item["size_bytes"] >= MIN_MOVIE_BYTES
    ]
    movie_candidates.sort(
        key=lambda item: (item["duration_seconds"], item["size_bytes"]),
        reverse=True,
    )

    report: dict[str, Any] = {
        "schema_version": 1,
        "created_at": iso_now(),
        "pipeline": "movie",
        "job": job_name,
        "title": title,
        "year": year,
        "source": str(folder),
        "source_files": [str(path) for path in files],
        "probes": probes,
        "probe_errors": probe_errors,
        "move_performed": False,
        "copy_performed": False,
    }

    status = "REVIEW"
    reason = ""
    selected: Path | None = None

    title_norm = norm(title)
    title_lower = title.casefold()

    if title_norm in GENERIC_TITLES:
        status = "REVIEW"
        reason = "The movie title is generic or unknown; automatic Jellyfin naming is unsafe."
    elif any(marker in title_lower for marker in MUSIC_COLLECTION_MARKERS):
        status = "REVIEW"
        reason = "The title appears to be a concert or music-video collection, not a normal movie."
    elif probe_errors:
        status = "RERIP"
        reason = "One or more files failed ffprobe."
    elif not movie_candidates:
        status = "REVIEW"
        reason = "No feature-length movie candidate passed the minimum runtime, size, and stream rules."
    else:
        best = movie_candidates[0]
        selected = Path(best["path"])
        if len(movie_candidates) > 1:
            second = movie_candidates[1]
            ratio = second["duration_seconds"] / max(best["duration_seconds"], 1)
            if ratio >= 0.85:
                status = "REVIEW"
                reason = "Multiple similarly long movie candidates were found."
        if not reason:
            short_titles = [
                item for item in probes
                if item["has_video"]
                and item["has_audio"]
                and 120 <= item["duration_seconds"] <= 30 * 60
            ]
            short_total = sum(item["duration_seconds"] for item in short_titles)
            if (
                len(short_titles) >= 2
                and best["duration_seconds"] > 0
                and abs(short_total - best["duration_seconds"]) / best["duration_seconds"] <= 0.15
            ):
                status = "REVIEW"
                reason = "The longest title resembles a combined play-all copy of several shorter videos."

        if not reason:
            decode_ok, decode_output = decode_check(selected)
            report["decode_check"] = {
                "ok": decode_ok,
                "output_tail": decode_output,
            }
            if not decode_ok:
                status = "RERIP"
                reason = "The selected movie failed a full ffmpeg decode."
            else:
                evidence = {
                    "title": title,
                    "year": year,
                    "selected": best,
                    "other_movie_candidates": movie_candidates[1:],
                    "decode_ok": decode_ok,
                    "source_folder": str(folder),
                }
                ai = ai_review(model, evidence)
                report["ai_review"] = ai
                status = ai["decision"]
                reason = ai["reason"]

    report["status"] = status
    report["reason"] = reason
    if selected:
        report["selected_source"] = str(selected)

    if status == "PASS" and selected:
        library_folder, target = destination_for(title, year, selected.suffix)
        report["target"] = str(target)
        if target.exists():
            try:
                existing = probe(target)
                selected_probe = next(p for p in probes if p["path"] == str(selected))
                same = (
                    abs(existing["duration_seconds"] - selected_probe["duration_seconds"]) <= 2
                    and existing["size_bytes"] == selected_probe["size_bytes"]
                )
            except Exception:
                same = False
            if same:
                status = "SKIP"
                reason = "An identical movie already exists in Jellyfin."
            else:
                status = "REVIEW"
                reason = "The Jellyfin destination exists but does not match the source."
        elif commit:
            atomic_copy_and_verify(selected, target)
            report["copy_performed"] = True
            report["move_performed"] = False
            status = "PASS"
            reason = "Validation passed and the verified movie was atomically copied into Jellyfin."
            report["jellyfin_refresh"] = refresh_jellyfin()
        else:
            reason = "Dry run passed; no Jellyfin copy was performed."
        report["status"] = status
        report["reason"] = reason

    if status in {"REVIEW", "BLOCK", "RERIP"} and commit:
        bundle = stage_bundle(status, job_name, files, report)
        report["staging_path"] = str(bundle)

    report_path = write_report(report)

    state["jobs"][job_id] = {
        "fingerprint": fp,
        "status": report["status"],
        "reason": report["reason"],
        "source": str(folder),
        "report_path": str(report_path),
        "updated_at": iso_now(),
    }
    if commit:
        save_state(state)
    return report


def discover(minimum_age: int) -> list[Path]:
    if not COMPLETED.exists():
        return []
    now = time.time()
    found: list[Path] = []
    for folder in COMPLETED.rglob("*"):
        if not folder.is_dir() or looks_like_tv(folder):
            continue
        files = video_files(folder)
        if not files:
            continue
        if any(parent in found for parent in folder.parents):
            continue
        newest = max(path.stat().st_mtime for path in files)
        if now - newest < minimum_age:
            continue
        found.append(folder)
    return sorted(found, key=lambda p: str(p).casefold())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Unattended post-ARM movie validation and Jellyfin import router."
    )
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--ai", default=MODEL_DEFAULT)
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--minimum-age", type=int, default=600)
    args = parser.parse_args()

    ensure_dirs()
    active, details = arm_active()
    if active:
        print(json.dumps({
            "status": "WAIT",
            "reason": "ARM processing is active.",
            "processes": details,
        }, indent=2))
        return 0

    commit = args.commit and not args.dry_run
    state = load_state()
    folders = [args.source] if args.source else discover(args.minimum_age)
    results = []
    for folder in folders:
        if not folder or not folder.exists():
            continue
        try:
            results.append(process_folder(folder, args.ai, commit, args.force, state))
        except Exception as exc:
            results.append({
                "status": "BLOCK",
                "source": str(folder),
                "reason": f"Unhandled router error: {exc}",
            })
    print(json.dumps({
        "status": "COMPLETE",
        "commit": commit,
        "jobs_seen": len(folders),
        "results": results,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
