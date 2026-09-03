#!/usr/bin/env bash
set -u

DEVICE="/dev/sr0"
SHOW="The Boondocks"

STATE="$HOME/rips/reports/boondocks-s3d2-last-staging.txt"
CONT_PIDFILE="$HOME/rips/reports/boondocks-s3d2-continuation.pid"

VALIDATOR="$HOME/rdp-scripts/Jarvis/media/jarvis_validate_rip.py"
MOVER="$HOME/rdp-scripts/Jarvis/media/jarvis_move_if_valid.py"

DEST="/mnt/media/Shows/The Boondocks/Season 03"
LOCK="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/jarvis-media-ingest.lock"

log() {
    printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

CONT_PID="$(cat "$CONT_PIDFILE" 2>/dev/null || true)"

if [[ -n "$CONT_PID" ]]; then
    log "Waiting for continuation PID $CONT_PID."

    while kill -0 "$CONT_PID" 2>/dev/null; do
        sleep 30
    done
fi

STAGE="$(cat "$STATE" 2>/dev/null || true)"

if [[ -z "$STAGE" || ! -d "$STAGE" ]]; then
    log "BLOCK: staging directory unavailable."
    exit 1
fi

FAILED="$STAGE/failed-attempts"
RESULT="$STAGE/validation_result.json"

mkdir -p "$FAILED"

valid() {
    local f="$1"

    [[ -s "$f" ]] || return 1

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

rescue() {
    local ep="$1"
    shift

    local out="$STAGE/The Boondocks - S03E${ep}.mkv"

    if valid "$out"; then
        log "SKIP: S03E${ep} already valid."
        return 0
    fi

    for title in "$@"; do
        log "RESCUE: S03E${ep} from Title $title using --no-dvdnav."

        rm -f "$out"

        if timeout \
             --foreground \
             --signal=INT \
             --kill-after=45s \
             45m \
             HandBrakeCLI \
               --no-dvdnav \
               -i "$DEVICE" \
               -t "$title" \
               -o "$out" \
               --format av_mkv \
               -e x264 \
               -q 19 \
               -B 160; then

            if valid "$out"; then
                log "PASS: S03E${ep} recovered from Title $title."
                return 0
            fi
        fi

        log "FAIL: rescue Title $title."

        [[ -f "$out" ]] && \
            mv "$out" "$FAILED/S03E${ep}-title-${title}-final-rescue-$(date +%H%M%S).mkv"
    done

    return 1
}

log "===== FINAL DISC RECOVERY ====="

rescue 06 7 5 || log "MISSING: S03E06"
rescue 08 29 30 || log "MISSING: S03E08"
rescue 10 6 8 || log "MISSING: S03E10"

log "===== FINAL INVENTORY ====="

GOOD=1

for ep in 06 07 08 09 10; do
    f="$STAGE/The Boondocks - S03E${ep}.mkv"

    if valid "$f"; then
        d="$(
            ffprobe -v error \
              -show_entries format=duration \
              -of default=noprint_wrappers=1:nokey=1 \
              "$f"
        )"
        log "PASS S03E${ep}: ${d}s"
    else
        log "MISSING S03E${ep}"
        GOOD=0
    fi
done

if [[ "$GOOD" -ne 1 ]]; then
    log "Recovery exhausted. No Jellyfin move attempted."
    exit 0
fi

log "Complete S03E06-E10 batch recovered."
log "Waiting for Jarvis validation lock."

exec 8>"$LOCK"
flock 8

python3 "$VALIDATOR" \
  --show "$SHOW" \
  --season 3 \
  --start 6 \
  --end 10 \
  --staging "$STAGE" \
  --write-result "$RESULT" \
  --ai llama3.2:3b

python3 "$MOVER" \
  --validation "$RESULT" \
  --destination "$DEST"

flock -u 8

log "===== DONE: VALIDATED AND MOVED TO JELLYFIN ====="
