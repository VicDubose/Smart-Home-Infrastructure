#!/usr/bin/env bash
set -u

DEVICE="/dev/sr0"
SHOW="The Boondocks"
DEST="/mnt/media/Shows/The Boondocks/Season 03"

VALIDATOR="$HOME/rdp-scripts/Jarvis/media/jarvis_validate_rip.py"
MOVER="$HOME/rdp-scripts/Jarvis/media/jarvis_move_if_valid.py"
LOCK="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/jarvis-media-ingest.lock"

STAMP="$(date +%Y%m%d-%H%M%S)"
ROOT="$HOME/rips/boondocks-s3d3-finish-$STAMP"
mkdir -p "$ROOT"

log() {
    printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

valid() {
    local f="$1"
    [[ -s "$f" ]] || return 1

    local d
    d="$(
        ffprobe -v error \
          -show_entries format=duration \
          -of default=noprint_wrappers=1:nokey=1 \
          "$f" 2>/dev/null || true
    )"

    [[ -n "$d" ]] || return 1

    python3 - "$d" <<'PY'
import sys
d=float(sys.argv[1])
raise SystemExit(0 if 1080 <= d <= 1800 else 1)
PY
}

try_title() {
    local ep="$1"
    local title="$2"
    local dir="$ROOT/S03E${ep}"
    local out="$dir/The Boondocks - S03E${ep}.mkv"

    mkdir -p "$dir"
    rm -f "$out"

    log "Trying S03E${ep} from Title ${title}"

    HandBrakeCLI \
      -i "$DEVICE" \
      -t "$title" \
      -o "$out" \
      --format av_mkv \
      -e x264 \
      -q 19 \
      -B 160 || true

    valid "$out"
}

publish() {
    local ep="$1"
    local dir="$ROOT/S03E${ep}"
    local num=$((10#$ep))
    local result="$dir/validation_result.json"

    exec 8>"$LOCK"
    flock 8

    python3 "$VALIDATOR" \
      --show "$SHOW" \
      --season 3 \
      --start "$num" \
      --end "$num" \
      --staging "$dir" \
      --write-result "$result" \
      --ai llama3.2:3b

    if [[ $? -eq 0 ]]; then
        python3 "$MOVER" \
          --validation "$result" \
          --destination "$DEST"
    fi

    flock -u 8
}

do_episode() {
    local ep="$1"
    local primary="$2"
    local fallback="$3"

    if try_title "$ep" "$primary"; then
        log "PASS RIP: S03E${ep} Title ${primary}"
        publish "$ep"
        return
    fi

    log "Primary failed; trying fallback Title ${fallback}"

    if try_title "$ep" "$fallback"; then
        log "PASS RIP: S03E${ep} Title ${fallback}"
        publish "$ep"
        return
    fi

    log "PARKED: S03E${ep} both titles failed."
}

do_episode 14 2 5
do_episode 15 3 6

log "===== DISC 3 FINISHER DONE ====="
