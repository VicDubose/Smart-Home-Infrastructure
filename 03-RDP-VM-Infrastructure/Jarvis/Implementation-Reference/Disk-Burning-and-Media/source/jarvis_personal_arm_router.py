#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

HOME = Path.home()
ARM_MEDIA = Path('/mnt/appdata/arm/media')
ARM_LOGS = Path('/mnt/appdata/arm/logs')
LIBRARY = Path('/mnt/media/Shows')
PROFILE_FILE = HOME / 'Jarvis/config/arm_handoff_profiles.json'
WORKER = HOME / 'rdp-scripts/Jarvis/media/jarvis_arm_handoff_worker.py'
STAGE_ROOT = ARM_MEDIA / 'personal-staging'
REPORT_ROOT = HOME / 'Jarvis/reports/personal-arm'
STATE_FILE = HOME / 'Jarvis/state/personal-arm-router.json'
VIDEO_EXTS = {'.mkv', '.mp4', '.m4v'}
FATAL_MARKERS = (
    'a fatal error has occurred',
    'error while running makemkv',
    'call to makemkv failed',
    'failed to save title',
    'libmkv_trace: exception',
    'input/output error',
)


def run(cmd, timeout=300):
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, timeout=timeout)


def norm(value):
    return re.sub(r'[^a-z0-9]+', ' ', value.casefold()).strip()


def profile_key(show, season, disc):
    return f'{norm(show)}|{season}|{disc}'


def safe_name(value):
    return re.sub(r'[^A-Za-z0-9._-]+', '-', value).strip('-') or 'job'


def natural_key(value):
    return [int(x) if x.isdigit() else x.casefold()
            for x in re.split(r'(\d+)', value)]


def ensure_dirs():
    for path in (STAGE_ROOT / 'rerip', STAGE_ROOT / 'review',
                 STAGE_ROOT / 'block', REPORT_ROOT, STATE_FILE.parent):
        path.mkdir(parents=True, exist_ok=True)


def arm_active():
    proc = run([
        'docker', 'exec', 'arm', 'bash', '-lc',
        "pgrep -af '[/]opt/arm/arm/ripper/main\\.py|[H]andBrakeCLI|[m]akemkvcon|[d]vdbackup|[f]fmpeg' || true",
    ], timeout=20)
    return bool(proc.stdout.strip()), proc.stdout.strip()


def find_log(show, season, disc):
    identity = norm(f'{show} S{season}D{disc}')
    shorthand = norm(f'S{season}D{disc}')
    aliases = {
        norm(show),
        norm(re.sub(r'^(?:the|a|an)\s+', '', show, flags=re.I)),
    }
    aliases.discard('')
    matches = []

    for path in ARM_LOGS.glob('*.log'):
        try:
            text = path.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue

        stem_norm = norm(path.stem)
        text_norm = norm(text)

        filename_match = (
            shorthand in stem_norm
            and any(alias in stem_norm for alias in aliases)
        )
        content_match = (
            identity in text_norm
            or (
                shorthand in text_norm
                and any(alias in text_norm for alias in aliases)
            )
        )

        if filename_match or content_match:
            matches.append(path)

    return max(matches, key=lambda p: p.stat().st_mtime) if matches else None


def parse_log(path):
    info = {
        'path': str(path) if path else None,
        'fatal': False,
        'fatal_markers': [],
        'found_titles': None,
        'video_type': None,
        'year': None,
    }

    if not path:
        return info

    text = path.read_text(encoding='utf-8', errors='ignore')
    low = text.casefold()

    extra_fatal_markers = (
        'failed to save title',
        'call to makemkv failed',
        'a fatal error has occurred',
        'error while running makemkv',
        'libmkv_trace: exception',
        'unrecovered read error',
        'id crc or ecc error',
        'posix error - input/output error',
    )

    candidates = tuple(FATAL_MARKERS) + extra_fatal_markers
    info['fatal_markers'] = sorted({
        marker for marker in candidates
        if marker.casefold() in low
    })
    info['fatal'] = bool(info['fatal_markers'])

    counts = [int(value) for value in re.findall(
        r'Found\s+(\d+)\s+titles',
        text,
        re.I,
    )]
    if counts:
        info['found_titles'] = max(counts)

    types = re.findall(r'video_type:\s*([^\s]+)', text, re.I)
    years = re.findall(r'\byear:\s*([^\s]+)', text, re.I)

    if types:
        info['video_type'] = types[-1]
    if years:
        info['year'] = years[-1]

    return info


def find_dirs(show, season, disc):
    needle = norm(f'{show} S{season}D{disc}')
    results = []
    for root in (ARM_MEDIA / 'completed', ARM_MEDIA / 'transcode', ARM_MEDIA / 'raw'):
        if not root.exists():
            continue
        for path in root.rglob('*'):
            if path.is_dir() and needle in norm(path.name):
                results.append(path)
    order = {'completed': 0, 'transcode': 1, 'raw': 2}
    return sorted(set(results), key=lambda p: (
        min((order.get(part, 9) for part in p.parts), default=9), str(p)))


def media_files(path):
    if not path or not path.exists():
        return []
    return sorted([p for p in path.rglob('*')
                   if p.is_file() and p.suffix.casefold() in VIDEO_EXTS],
                  key=lambda p: natural_key(p.name))


def choose_sources(paths):
    selected = {'completed': (None, []), 'transcode': (None, []), 'raw': (None, [])}
    for path in paths:
        files = media_files(path)
        if not files:
            continue
        bucket = 'completed' if 'completed' in path.parts else (
            'transcode' if 'transcode' in path.parts else 'raw')
        if not selected[bucket][1]:
            selected[bucket] = (path, files)
    return selected


def container_path(path):
    base = str(ARM_MEDIA)
    value = str(path)
    if not value.startswith(base + os.sep):
        raise ValueError(f'Outside ARM media root: {path}')
    return '/home/arm/media' + value[len(base):]


def probe(path):
    proc = run([
        'docker', 'exec', 'arm', 'ffprobe', '-v', 'error',
        '-show_entries',
        'format=duration,size:stream=codec_type,codec_name,width,height,channels',
        '-of', 'json', container_path(path),
    ], timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or 'ffprobe failed')
    data = json.loads(proc.stdout)
    fmt = data.get('format', {})
    streams = data.get('streams', [])
    return {
        'path': str(path),
        'duration_seconds': float(fmt.get('duration') or 0),
        'size_bytes': int(fmt.get('size') or path.stat().st_size),
        'has_video': any(s.get('codec_type') == 'video' for s in streams),
        'has_audio': any(s.get('codec_type') == 'audio' for s in streams),
    }


def existing_episodes(show, season):
    season_dir = LIBRARY / show / f'Season {season:02d}'
    found = set()
    pattern = re.compile(rf'S0*{season}E0*(\d+)', re.I)
    if season_dir.exists():
        for path in season_dir.rglob('*'):
            if path.is_file():
                match = pattern.search(path.name)
                if match:
                    found.add(int(match.group(1)))
    return found


def infer_episode_range(show, season, count):
    existing = existing_episodes(show, season)
    start = 1
    while start in existing:
        start += 1
    proposed = list(range(start, start + count))
    if any(ep in existing for ep in proposed):
        raise RuntimeError('Next missing episodes are not one clean contiguous block.')
    return proposed[0], proposed[-1]


def load_profiles():
    if not PROFILE_FILE.exists():
        return {'version': 1, 'defaults': {'ai_model': 'llama3:8b',
                'minimum_source_age_seconds': 600,
                'library_root': '/mnt/media/Shows'}, 'tv_discs': {}}
    return json.loads(PROFILE_FILE.read_text(encoding='utf-8'))


def ensure_profile(show, season, disc, probes, model):
    doc = load_profiles()
    tv_discs = doc.setdefault('tv_discs', {})
    key = profile_key(show, season, disc)
    if isinstance(tv_discs.get(key), dict):
        return tv_discs[key], False

    durations = [p['duration_seconds'] / 60 for p in probes]
    if not durations or any(d < 15 or d > 90 for d in durations):
        raise RuntimeError('TV candidates are outside the safe 15–90 minute range.')
    if max(durations) - min(durations) > 12:
        raise RuntimeError('TV title runtimes vary too widely for automatic mapping.')

    start, end = infer_episode_range(show, season, len(probes))
    profile = {
        'show': show,
        'season': season,
        'disc': disc,
        'start_episode': start,
        'end_episode': end,
        'minimum_runtime_minutes': max(10, math.floor(min(durations)) - 3),
        'maximum_runtime_minutes': math.ceil(max(durations)) + 3,
        'ai_model': model,
        'enabled': True,
    }
    stamp = time.strftime('%Y%m%d-%H%M%S')
    if PROFILE_FILE.exists():
        shutil.copy2(PROFILE_FILE, PROFILE_FILE.with_name(PROFILE_FILE.name + f'.bak-{stamp}'))
    tv_discs[key] = profile
    tmp = PROFILE_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(doc, indent=4, sort_keys=True) + '\n', encoding='utf-8')
    tmp.replace(PROFILE_FILE)
    return profile, True


def fingerprint(files, log_path):
    h = hashlib.sha256()
    for path in files:
        st = path.stat()
        h.update(f'{path}|{st.st_size}|{st.st_mtime_ns}\n'.encode())
    if log_path and log_path.exists():
        st = log_path.stat()
        h.update(f'{log_path}|{st.st_size}|{st.st_mtime_ns}\n'.encode())
    return h.hexdigest()


def load_state():
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {}


def save_state(state):
    tmp = STATE_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    tmp.replace(STATE_FILE)


def stage_bundle(status, job, files, report):
    import json as _json
    import os as _os
    import shutil as _shutil
    from datetime import datetime as _datetime
    from pathlib import Path as _Path

    bucket = {
        'RERIP': 'rerip',
        'REVIEW': 'review',
        'BLOCK': 'block',
    }.get(str(status).upper(), 'review')

    stamp = _datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')
    bundle = STAGE_ROOT / bucket / f'{safe_name(job)}-{stamp}'
    media = bundle / 'media'
    media.mkdir(parents=True, exist_ok=False)

    used_names = set()

    for index, item in enumerate(files, start=1):
        if isinstance(item, dict):
            source_value = item.get('path')
        else:
            source_value = item

        if not source_value:
            continue

        source = _Path(source_value)
        if not source.is_file():
            continue

        name = source.name
        if name in used_names:
            name = f'{index:02d}-{name}'
        used_names.add(name)

        target = media / name

        try:
            _os.link(source, target)
        except OSError:
            _shutil.copy2(source, target)

    staged_report = dict(report)
    staged_report['staging_path'] = str(bundle)

    (bundle / 'report.json').write_text(
        _json.dumps(staged_report, indent=2, sort_keys=True),
        encoding='utf-8',
    )

    (bundle / 'report.txt').write_text(
        f"Status: {status}\n"
        f"Job: {job}\n"
        f"Reason: {staged_report.get('reason', 'Unspecified')}\n"
        f"Source preserved: YES\n"
        f"Jellyfin move: NO\n",
        encoding='utf-8',
    )

    return bundle


def expected_targets(show, season, profile):
    season_dir = LIBRARY / show / f'Season {season:02d}'
    return [season_dir / f'{show} - S{season:02d}E{ep:02d}.mkv'
            for ep in range(int(profile['start_episode']),
                            int(profile['end_episode']) + 1)]


def process(show, season, disc, model, commit, force):
    ensure_dirs()
    active, details = arm_active()
    if active:
        return {'status': 'WAIT', 'reason': 'ARM is active', 'processes': details}

    job = f'{show} S{season}D{disc}'
    log_path = find_log(show, season, disc)
    log_info = parse_log(log_path)
    sources = choose_sources(find_dirs(show, season, disc))
    completed_dir, completed = sources['completed']
    transcode_dir, transcode = sources['transcode']
    raw_dir, raw = sources['raw']
    all_files = completed or transcode or raw

    state = load_state()
    key = profile_key(show, season, disc)
    fp = fingerprint(all_files, log_path)
    if not force and state.get(key, {}).get('fingerprint') == fp:
        return {'status': 'SKIP', 'reason': 'Unchanged job already handled',
                'previous': state[key]}

    probes = []
    probe_errors = []
    for path in all_files:
        try:
            probes.append(probe(path))
        except Exception as exc:
            probe_errors.append(f'{path}: {exc}')

    report = {
        'schema_version': 1,
        'job': job,
        'pipeline': 'tv',
        'show': show,
        'season': season,
        'disc': disc,
        'arm_log': log_info,
        'completed_source': str(completed_dir) if completed_dir else None,
        'transcode_source': str(transcode_dir) if transcode_dir else None,
        'raw_source': str(raw_dir) if raw_dir else None,
        'files': probes,
        'probe_errors': probe_errors,
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'move_performed': False,
    }

    if log_info['fatal']:
        found = log_info.get('found_titles')
        detail = f'{len(all_files)} file(s) recovered'
        if found:
            detail += f' from {found} detected title(s)'
        status = 'RERIP'
        reason = f'ARM fatal read/MakeMKV failure; {detail}. Partial files cannot enter Jellyfin.'
    elif not completed:
        status = 'REVIEW'
        reason = 'ARM did not produce completed media; output exists only in raw/transcode or is absent.'
    elif probe_errors:
        status = 'BLOCK'
        reason = 'One or more completed files failed ffprobe.'
    elif any(not p['has_video'] or not p['has_audio'] for p in probes):
        status = 'BLOCK'
        reason = 'One or more completed files are missing video or audio.'
    else:
        status = 'READY'
        reason = 'Technical pre-check passed; ready for Jarvis guarded validation.'

    report['status'] = status
    report['reason'] = reason
    report_path = REPORT_ROOT / f'{safe_name(job)}-{time.strftime("%Y%m%d-%H%M%S")}.json'

    if commit and status in {'RERIP', 'REVIEW', 'BLOCK'}:
        stage = stage_bundle(status, job, all_files, report)
        report['staging_path'] = str(stage)

    if commit and status == 'READY':
        try:
            profile, created = ensure_profile(show, season, disc, probes, model)
            report['profile'] = profile
            report['profile_created'] = created
            worker = run(['python3', '-u', str(WORKER)], timeout=7200)
            report['worker_returncode'] = worker.returncode
            report['worker_output_tail'] = (worker.stdout + '\n' + worker.stderr)[-12000:]
            targets = expected_targets(show, season, profile)
            report['expected_targets'] = [str(x) for x in targets]
            if worker.returncode == 0 and all(x.exists() for x in targets):
                report['status'] = 'PASS'
                report['reason'] = 'Jarvis validation passed and all expected Jellyfin targets exist.'
                report['move_performed'] = True
            else:
                report['status'] = 'REVIEW'
                report['reason'] = 'Jarvis did not confirm every expected Jellyfin target.'
                remaining = media_files(completed_dir) if completed_dir else []
                stage = stage_bundle('REVIEW', job, remaining, report)
                report['staging_path'] = str(stage)
        except Exception as exc:
            report['status'] = 'BLOCK'
            report['reason'] = f'Automatic profile/validation gate stopped safely: {exc}'
            stage = stage_bundle('BLOCK', job, completed, report)
            report['staging_path'] = str(stage)

    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n',
                           encoding='utf-8')
    report['report_path'] = str(report_path)
    state[key] = {
        'fingerprint': fp,
        'status': report['status'],
        'reason': report['reason'],
        'report_path': str(report_path),
        'staging_path': report.get('staging_path'),
        'processed_at': report['created_at'],
    }
    save_state(state)
    return report


def scan(model, commit, hours, force):
    cutoff = time.time() - hours * 3600
    jobs = {}
    title_re = re.compile(r'(?:title is|title:)\s*(.+)', re.I)
    id_re = re.compile(r'^(.*?)\s+S0*(\d+)\s*D0*(\d+)\b', re.I)
    for log in ARM_LOGS.glob('*.log'):
        try:
            if log.stat().st_mtime < cutoff:
                continue
            text = log.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        for title in title_re.findall(text):
            match = id_re.search(re.sub(r'\s*\([^)]*\)\s*$', '', title).strip())
            if match:
                identity = (match.group(1).strip(), int(match.group(2)), int(match.group(3)))
                jobs[profile_key(*identity)] = identity
    return [process(*identity, model=model, commit=commit, force=force)
            for identity in sorted(jobs.values(), key=lambda x: (norm(x[0]), x[1], x[2]))]


def main():
    parser = argparse.ArgumentParser(description='Personal ARM to Jarvis validation router')
    parser.add_argument('--show')
    parser.add_argument('--season', type=int)
    parser.add_argument('--disc', type=int)
    parser.add_argument('--scan', action='store_true')
    parser.add_argument('--since-hours', type=int, default=36)
    parser.add_argument('--ai', default='llama3:8b')
    parser.add_argument('--commit', action='store_true')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()

    if args.scan:
        result = scan(args.ai, args.commit, args.since_hours, args.force)
    else:
        if not args.show or args.season is None or args.disc is None:
            parser.error('Use --scan or supply --show, --season, and --disc.')
        result = process(args.show, args.season, args.disc,
                         args.ai, args.commit, args.force)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
