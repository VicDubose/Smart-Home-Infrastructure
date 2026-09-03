#!/usr/bin/env bash
set -u

DEVICE="/dev/sr0"
SHOW="The Boondocks"
DEST="/mnt/media/Shows/The Boondocks/Season 03"

VALIDATOR="$HOME/rdp-scripts/Jarvis/media/jarvis_validate_rip.py"
MOVER="$HOME/rdp-scripts/Jarvis/media/jarvis_move_if_valid.py"
LOCK="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/jarvis-media-ingest.lock"

STAMP="$(date +%Y%m%d-%H%M%S)"
ROOT="$HOME/rips/boondocks-s3d1-$STAMP"
FAILED="$ROOT/failed-attempts"

mkdir -p "$ROOT" "$FAILED"

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
raise SystemExit(0 if 1200 <= d <= 1500 else 1)
PY
}

try_title() {
    local ep="$1"
    local title="$2"

    local dir="$ROOT/S03E${ep}"
    local out="$dir/The Boondocks - S03E${ep}.mkv"

    mkdir -p "$dir"
    rm -f "$out"

    log "RIP: S03E${ep} from Title ${title} using --no-dvdnav"

    if timeout \
        --foreground \
        --signal=INT \
        --kill-after=45s \
        20m \
        HandBrakeCLI \
          --no-dvdnav \
          -i "$DEVICE" \
          -t "$title" \
          -o "$out" \
          --format av_mkv \
          -e x264 \
          -q 19 \
          -B 160
    then
        if valid "$out"; then
            log "PASS RIP: S03E${ep} Title ${title}"
            return 0
        fi
    fi

    if [[ -e "$out" ]]; then
        mv "$out" \
          "$FAILED/S03E${ep}-title-${title}-failed.mkv"
    fi

    log "FAIL: S03E${ep} Title ${title}"
    return 1
}

publish() {
    local ep="$1"
    local num=$((10#$ep))
    local dir="$ROOT/S03E${ep}"
    local result="$dir/validation_result.json"

    log "Sending S03E${ep} to Jarvis"

    exec 8>"$LOCK"
    flock 8

    if python3 "$VALIDATOR" \
        --show "$SHOW" \
        --season 3 \
        --start "$num" \
        --end "$num" \
        --staging "$dir" \
        --write-result "$result" \
        --ai llama3.2:3b
    then
        python3 "$MOVER" \
          --validation "$result" \
          --destination "$DEST"
    else
        log "JARVIS BLOCKED S03E${ep}"
    fi

    flock -u 8
}

do_episode() {
    local ep="$1"
    local primary="$2"
    local fallback="$3"

    log "===== S03E${ep} ====="

    if try_title "$ep" "$primary"; then
        publish "$ep"
        return
    fi

    log "Trying duplicate fallback Title ${fallback}"

    if try_title "$ep" "$fallback"; then
        publish "$ep"
        return
    fi

    log "PARKED: S03E${ep} could not be recovered."
}

LABEL="$(lsblk -no LABEL "$DEVICE" 2>/dev/null || true)"
log "Disc label: $LABEL"

if [[ "${LABEL^^}" != *"BOONDOCKS_S3_D1"* ]]; then
    log "BLOCK: Wrong disc in $DEVICE"
    exit 1
fi

# Disc 1 mapping
do_episode 01 5 7
do_episode 02 1 3
do_episode 03 30 31
do_episode 04 2 4
do_episode 05 6 8

echo
log "===== DISC 1 WORK COMPLETE ====="

echo
echo "===== JELLYFIN SEASON 3 ====="

for ep in $(seq -w 1 15); do
    f="$DEST/The Boondocks - S03E${ep}.mkv"

    if [[ -s "$f" ]]; then
        echo "S03E${ep} ✅"
    else
        echo "S03E${ep} ❌"
    fi
done

echo
log "Working directory: $ROOT"
