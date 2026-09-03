#!/usr/bin/env bash
set -u

DEVICE="/dev/sr0"
SHOW="Danny Phantom"
DEST="/mnt/media/Shows/Danny Phantom/Season 03"

VALIDATOR="$HOME/rdp-scripts/Jarvis/media/jarvis_validate_rip.py"
MOVER="$HOME/rdp-scripts/Jarvis/media/jarvis_move_if_valid.py"
LOCK="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/jarvis-media-ingest.lock"

STAMP="$(date +%Y%m%d-%H%M%S)"
ROOT="$HOME/rips/danny-phantom-s3-final-$STAMP"
FAILED="$ROOT/failed-attempts"

mkdir -p "$ROOT" "$FAILED" "$DEST"

log() {
    printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

valid_normal() {
    local f="$1"
    [[ -s "$f" ]] || return 1

    local d
    d="$(ffprobe -v error \
        -show_entries format=duration \
        -of default=nw=1:nk=1 \
        "$f" 2>/dev/null || true)"

    [[ -n "$d" ]] || return 1

    python3 - "$d" <<'PY'
import sys
d=float(sys.argv[1])
raise SystemExit(0 if 1200 <= d <= 1800 else 1)
PY
}

valid_finale() {
    local f="$1"
    [[ -s "$f" ]] || return 1

    local d
    d="$(ffprobe -v error \
        -show_entries format=duration \
        -of default=nw=1:nk=1 \
        "$f" 2>/dev/null || true)"

    [[ -n "$d" ]] || return 1

    python3 - "$d" <<'PY'
import sys
d=float(sys.argv[1])
raise SystemExit(0 if 2700 <= d <= 3300 else 1)
PY
}

rip_title() {
    local label="$1"
    local title="$2"
    local out="$3"
    local mode="$4"

    log "RIP: $label from DVD Title $title"

    if timeout --foreground --signal=INT --kill-after=45s 20m \
        HandBrakeCLI \
          -i "$DEVICE" \
          -t "$title" \
          -o "$out" \
          --format av_mkv \
          -e x264 \
          -q 19 \
          -B 160
    then
        if [[ "$mode" == "finale" ]]; then
            valid_finale "$out" && return 0
        else
            valid_normal "$out" && return 0
        fi
    fi

    log "Normal dvdnav failed — retrying $label with --no-dvdnav"

    if [[ -e "$out" ]]; then
        mv "$out" "$FAILED/${label// /_}-dvdnav-failed.mkv"
    fi

    if timeout --foreground --signal=INT --kill-after=45s 20m \
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
        if [[ "$mode" == "finale" ]]; then
            valid_finale "$out" && return 0
        else
            valid_normal "$out" && return 0
        fi
    fi

    if [[ -e "$out" ]]; then
        mv "$out" "$FAILED/${label// /_}-nodvdnav-failed.mkv"
    fi

    return 1
}

publish_normal() {
    local ep="$1"
    local dir="$ROOT/S03E${ep}"
    local result="$dir/validation_result.json"

    exec 8>"$LOCK"
    flock 8

    if python3 "$VALIDATOR" \
        --show "$SHOW" \
        --season 3 \
        --start "$((10#$ep))" \
        --end "$((10#$ep))" \
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

do_normal() {
    local ep="$1"
    local title="$2"

    local dir="$ROOT/S03E${ep}"
    local out="$dir/Danny Phantom - S03E${ep}.mkv"

    mkdir -p "$dir"

    if rip_title "S03E${ep}" "$title" "$out" normal; then
        log "PASS RIP: S03E${ep}"
        publish_normal "$ep"
    else
        log "PARKED: S03E${ep} failed"
    fi
}

LABEL="$(lsblk -no LABEL "$DEVICE" 2>/dev/null || true)"
log "Disc label: $LABEL"

if [[ "${LABEL^^}" != *"DANNY_PHANTOM_S4_D1"* ]]; then
    log "BLOCK: unexpected disc in $DEVICE"
    exit 1
fi

# Missing normal episodes
do_normal 09 4
do_normal 10 7
do_normal 11 6

# Double-length series finale
FDIR="$ROOT/S03E12-E13"
FOUT="$FDIR/Danny Phantom - S03E12-E13.mkv"
mkdir -p "$FDIR"

if rip_title "S03E12-E13" 5 "$FOUT" finale; then
    log "PASS RIP: Phantom Planet"

    DURATION="$(ffprobe -v error \
        -show_entries format=duration \
        -of default=nw=1:nk=1 \
        "$FOUT")"

    SIZE="$(stat -c '%s' "$FOUT")"

    {
        echo "Danny Phantom finale technical exception"
        echo "Disc label: $LABEL"
        echo "DVD title: 5"
        echo "Episodes: S03E12-E13"
        echo "Duration: $DURATION"
        echo "Size: $SIZE"
        echo "Technical result: PASS"
    } > "$FDIR/validation_result.txt"

    exec 8>"$LOCK"
    flock 8

    FINAL_DEST="$DEST/Danny Phantom - S03E12-E13.mkv"

    if [[ -e "$FINAL_DEST" ]]; then
        log "BLOCK: finale already exists at destination"
    else
        mv "$FOUT" "$FINAL_DEST"
        log "MOVE APPROVED: Phantom Planet -> $FINAL_DEST"
    fi

    flock -u 8
else
    log "PARKED: Phantom Planet failed"
fi

echo
log "===== DANNY PHANTOM FINAL DISC COMPLETE ====="

echo
echo "===== SEASON 03 FILES ====="
find "$DEST" \
  -maxdepth 1 \
  -type f \
  -iname 'Danny Phantom - S03E*.mkv' \
  -printf '%f\n' | sort

echo
log "Working directory: $ROOT"
