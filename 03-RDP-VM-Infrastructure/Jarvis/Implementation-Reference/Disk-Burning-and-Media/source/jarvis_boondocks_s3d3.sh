#!/usr/bin/env bash
set -Eeuo pipefail

DEVICE="/dev/sr0"
SHOW="The Boondocks"
DEST="/mnt/media/Shows/The Boondocks/Season 03"

VALIDATOR="$HOME/rdp-scripts/Jarvis/media/jarvis_validate_rip.py"
MOVER="$HOME/rdp-scripts/Jarvis/media/jarvis_move_if_valid.py"

STAMP="$(date +%Y%m%d-%H%M%S)"
STAGE="$HOME/rips/boondocks-s3d3-$STAMP"
FAILED="$STAGE/failed-attempts"
RESULT="$STAGE/validation_result.json"
LOCK="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/jarvis-media-ingest.lock"

mkdir -p "$STAGE" "$FAILED"

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

rip_title() {
    local ep="$1"
    local title="$2"
    local out="$STAGE/The Boondocks - S03E${ep}.mkv"

    rm -f "$out"

    log "RIP: S03E${ep} from DVD Title ${title}"

    if HandBrakeCLI \
        -i "$DEVICE" \
        -t "$title" \
        -o "$out" \
        --format av_mkv \
        -e x264 \
        -q 19 \
        -B 160
    then
        if valid "$out"; then
            log "PASS: S03E${ep} from Title ${title}"
            return 0
        fi
    fi

    if [[ -e "$out" ]]; then
        mv "$out" \
          "$FAILED/S03E${ep}-title-${title}-failed.mkv"
    fi

    log "FAIL: S03E${ep} from Title ${title}"
    return 1
}

rip_episode() {
    local ep="$1"
    local primary="$2"
    local fallback="$3"

    if rip_title "$ep" "$primary"; then
        return 0
    fi

    log "Trying fallback Title ${fallback} for S03E${ep}"
    rip_title "$ep" "$fallback"
}

log "===== BOONDOCKS S3 DISC 3 ====="

LABEL="$(lsblk -no LABEL "$DEVICE" 2>/dev/null || true)"
log "Disc label: $LABEL"

if [[ "$LABEL" != *"BOONDOCKS_S3_D3"* ]]; then
    log "BLOCK: wrong disc in $DEVICE"
    exit 1
fi

rip_episode 11 1 4
rip_episode 12 7 9
rip_episode 13 8 10
rip_episode 14 2 5
rip_episode 15 3 6

log "===== ALL FIVE RIPS COMPLETE ====="

for ep in 11 12 13 14 15; do
    f="$STAGE/The Boondocks - S03E${ep}.mkv"

    if ! valid "$f"; then
        log "BLOCK: S03E${ep} missing or invalid"
        exit 1
    fi

    ffprobe -v error \
      -show_entries format=duration \
      -of default=noprint_wrappers=1:nokey=1 \
      "$f" |
      xargs printf "S03E${ep}: %s seconds\n"
done

log "Waiting for Jarvis validation lock."

exec 8>"$LOCK"
flock 8

python3 "$VALIDATOR" \
  --show "$SHOW" \
  --season 3 \
  --start 11 \
  --end 15 \
  --staging "$STAGE" \
  --write-result "$RESULT" \
  --ai llama3.2:3b

python3 "$MOVER" \
  --validation "$RESULT" \
  --destination "$DEST"

flock -u 8

log "===== S3 DISC 3 COMPLETE ====="
log "Staging: $STAGE"
