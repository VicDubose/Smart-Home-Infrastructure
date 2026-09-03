#!/usr/bin/env bash
set -u

DEVICE="/dev/sr0"

MOVIE="Happy Halloween, Scooby-Doo!"
YEAR="2020"

STAMP="$(date +%Y%m%d-%H%M%S)"
ROOT="$HOME/rips/scooby-happy-halloween-$STAMP"
FAILED="$ROOT/failed-attempts"

OUT="$ROOT/$MOVIE ($YEAR).mkv"

DESTDIR="/mnt/media/Movies/General/Unrated/$MOVIE ($YEAR)"
DEST="$DESTDIR/$MOVIE ($YEAR).mkv"

LOCK="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/jarvis-media-ingest.lock"

mkdir -p "$ROOT" "$FAILED"

log() {
    printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

valid_movie() {
    local f="$1"

    [[ -s "$f" ]] || return 1

    local dur
    dur="$(
        ffprobe -v error \
          -show_entries format=duration \
          -of default=nw=1:nk=1 \
          "$f" 2>/dev/null || true
    )"

    [[ -n "$dur" ]] || return 1

    echo "Detected runtime: $dur seconds"

    python3 - "$dur" <<'PY'
import sys
d=float(sys.argv[1])

# Happy Halloween, Scooby-Doo! is ~76 minutes.
raise SystemExit(0 if 4400 <= d <= 4800 else 1)
PY
}

log "===== SCOOBY-DOO DISC 3 FINAL MOVIE ====="

LABEL="$(lsblk -no LABEL "$DEVICE" 2>/dev/null || true)"
log "Disc label: $LABEL"

if [[ "${LABEL^^}" != *"BEST_OF_WB100TH_SD_D3"* ]]; then
    log "BLOCK: Unexpected disc in $DEVICE"
    exit 1
fi

log "Ripping Title 1 -> $MOVIE ($YEAR)"

if timeout \
    --foreground \
    --signal=INT \
    --kill-after=45s \
    30m \
    HandBrakeCLI \
      -i "$DEVICE" \
      -t 1 \
      -o "$OUT" \
      --format av_mkv \
      -e x264 \
      -q 19 \
      -B 160
then
    if valid_movie "$OUT"; then
        log "PASS: Title 1 ripped successfully"
    else
        log "Normal rip produced invalid runtime"
        mv "$OUT" "$FAILED/title1-dvdnav-invalid.mkv"
    fi
fi

if ! valid_movie "$OUT" 2>/dev/null; then

    log "Retrying Title 1 with --no-dvdnav"

    rm -f "$OUT"

    if ! timeout \
        --foreground \
        --signal=INT \
        --kill-after=45s \
        30m \
        HandBrakeCLI \
          --no-dvdnav \
          -i "$DEVICE" \
          -t 1 \
          -o "$OUT" \
          --format av_mkv \
          -e x264 \
          -q 19 \
          -B 160
    then
        log "FAIL: --no-dvdnav rip failed"
        exit 1
    fi
fi

if ! valid_movie "$OUT"; then
    log "FAIL: final file failed runtime validation"
    exit 1
fi

mkdir -p "$DESTDIR"

exec 8>"$LOCK"
flock 8

if [[ -e "$DEST" ]]; then
    log "BLOCK: Destination already exists:"
    log "$DEST"
    flock -u 8
    exit 1
fi

mv "$OUT" "$DEST"

flock -u 8

log "===== MOVE COMPLETE ====="
log "$DEST"

echo
ffprobe -v error \
  -show_entries format=duration,size \
  -of default=nw=1 \
  "$DEST"

echo
log "===== HAPPY HALLOWEEN SCOOBY-DOO COMPLETE ====="
