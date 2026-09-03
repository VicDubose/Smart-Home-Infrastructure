#!/usr/bin/env bash
set -u

SHOW="The Boondocks"
DEVICE="/dev/sr0"

PIDFILE="$HOME/rips/reports/boondocks-s3d2-unattended.pid"
STATE="$HOME/rips/reports/boondocks-s3d2-last-staging.txt"

VALIDATOR="$HOME/rdp-scripts/Jarvis/media/jarvis_validate_rip.py"
MOVER="$HOME/rdp-scripts/Jarvis/media/jarvis_move_if_valid.py"
PIPE="$HOME/rdp-scripts/Jarvis/media/jarvis_disc_ingest_guarded_v2.py"

DEST="/mnt/media/Shows/The Boondocks/Season 03"

LOCK="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/jarvis-media-ingest.lock"

log() {
    printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

###############################################################################
# WAIT FOR ORIGINAL WORKER
###############################################################################

ORIGINAL_PID="$(cat "$PIDFILE" 2>/dev/null || true)"

if [[ -n "$ORIGINAL_PID" ]]; then
    log "Waiting for original S3D2 worker PID $ORIGINAL_PID."

    while kill -0 "$ORIGINAL_PID" 2>/dev/null; do
        sleep 30
    done
fi

STAGE="$(cat "$STATE" 2>/dev/null || true)"

if [[ -z "$STAGE" || ! -d "$STAGE" ]]; then
    log "BLOCK: original staging directory cannot be located."
    exit 1
fi

FAILED="$STAGE/failed-attempts"
RESULT="$STAGE/validation_result.json"

mkdir -p "$FAILED"

log "Original worker finished."
log "Continuation staging: $STAGE"


###############################################################################
# HELPERS
###############################################################################

valid_file() {
    local file="$1"

    [[ -s "$file" ]] || return 1

    local duration
    duration="$(
        ffprobe -v error \
          -show_entries format=duration \
          -of default=noprint_wrappers=1:nokey=1 \
          "$file" 2>/dev/null || true
    )"

    [[ -n "$duration" ]] || return 1

    python3 - "$duration" <<'PY'
import sys
d = float(sys.argv[1])
raise SystemExit(0 if 1200 <= d <= 1500 else 1)
PY
}

episode_done() {
    local ep="$1"

    local staged="$STAGE/The Boondocks - S03E${ep}.mkv"
    local library="$DEST/The Boondocks - S03E${ep}.mkv"

    valid_file "$staged" && return 0
    valid_file "$library" && return 0

    return 1
}

pipeline_rip() {
    local title="$1"
    local output="$2"

    timeout \
      --foreground \
      --signal=INT \
      --kill-after=45s \
      55m \
      python3 - "$DEVICE" "$title" "$output" "$PIPE" <<'PY'
import importlib.util
import sys
from pathlib import Path

device = sys.argv[1]
title = int(sys.argv[2])
output = Path(sys.argv[3])
pipeline = Path(sys.argv[4])

spec = importlib.util.spec_from_file_location(
    "jarvis_guarded_v2_continue",
    pipeline,
)

module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

try:
    module.rip_title(device, title, output)
except SystemExit as exc:
    code = exc.code if isinstance(exc.code, int) else 1
    raise SystemExit(code)
PY
}

preserve_failed() {
    local ep="$1"
    local title="$2"
    local file="$3"
    local mode="$4"

    if [[ -f "$file" ]]; then
        mv \
          "$file" \
          "$FAILED/S03E${ep}-title-${title}-${mode}-failed-$(date +%H%M%S).mkv"
    fi
}

normal_episode() {
    local ep="$1"
    shift

    if episode_done "$ep"; then
        log "SKIP: S03E${ep} is already complete."
        return 0
    fi

    local output="$STAGE/The Boondocks - S03E${ep}.mkv"

    for title in "$@"; do
        log "Trying S03E${ep} using normal Title $title."

        if pipeline_rip "$title" "$output"; then
            if valid_file "$output"; then
                log "PASS: S03E${ep} completed using Title $title."
                return 0
            fi
        fi

        log "FAIL: normal Title $title did not produce a valid episode."
        preserve_failed "$ep" "$title" "$output" "normal"
    done

    return 1
}

nodvdnav_episode() {
    local ep="$1"
    shift

    if episode_done "$ep"; then
        log "SKIP: S03E${ep} is already complete."
        return 0
    fi

    if ! HandBrakeCLI --help 2>&1 | grep -q -- '--no-dvdnav'; then
        log "SKIP: this HandBrake build does not advertise --no-dvdnav."
        return 1
    fi

    local output="$STAGE/The Boondocks - S03E${ep}.mkv"

    for title in "$@"; do
        log "RESCUE: S03E${ep} Title $title with --no-dvdnav."

        rm -f "$output"

        if timeout \
             --foreground \
             --signal=INT \
             --kill-after=45s \
             55m \
             HandBrakeCLI \
               --no-dvdnav \
               -i "$DEVICE" \
               -t "$title" \
               -o "$output" \
               --format av_mkv \
               -e x264 \
               -q 19 \
               -B 160; then

            if valid_file "$output"; then
                log "PASS: S03E${ep} rescued from Title $title."
                return 0
            fi
        fi

        log "FAIL: --no-dvdnav Title $title failed."
        preserve_failed "$ep" "$title" "$output" "nodvdnav"
    done

    return 1
}


###############################################################################
# IF ORIGINAL JOB COMPLETED, DON'T REDO ANYTHING
###############################################################################

COMPLETE=1

for ep in 06 07 08 09 10; do
    episode_done "$ep" || COMPLETE=0
done

if [[ "$COMPLETE" -eq 1 ]]; then
    log "All five episodes already exist. Continuation has nothing to do."
    exit 0
fi


###############################################################################
# GET EVERYTHING ELSE OFF THE DISC FIRST
###############################################################################

log "===== CONTINUING AVAILABLE EPISODES ====="

normal_episode 08 29 30 || \
    log "WARNING: S03E08 could not be recovered."

normal_episode 10 6 8 || \
    log "WARNING: S03E10 could not be recovered."


###############################################################################
# THEN GIVE THE TROUBLESOME E06 ONE ALTERNATE READ METHOD
###############################################################################

if ! episode_done 06; then
    log "===== E06 ALTERNATE READ RECOVERY ====="

    nodvdnav_episode 06 7 5 || \
        log "WARNING: S03E06 remains unrecoverable."
fi


###############################################################################
# REPORT WHAT WE ACTUALLY MANAGED TO SAVE
###############################################################################

log "===== RECOVERY INVENTORY ====="

ALL_GOOD=1

for ep in 06 07 08 09 10; do
    file="$STAGE/The Boondocks - S03E${ep}.mkv"

    if valid_file "$file"; then
        duration="$(
            ffprobe -v error \
              -show_entries format=duration \
              -of default=noprint_wrappers=1:nokey=1 \
              "$file"
        )"

        log "PASS S03E${ep}: ${duration}s"
    elif episode_done "$ep"; then
        log "PASS S03E${ep}: already in library"
    else
        log "MISSING S03E${ep}"
        ALL_GOOD=0
    fi
done


###############################################################################
# ONLY VALIDATE/MOVE WHEN THE ENTIRE DISC IS COMPLETE
###############################################################################

if [[ "$ALL_GOOD" -ne 1 ]]; then
    log "Partial recovery completed."
    log "No Jellyfin move attempted because the complete five-episode batch is not available."
    exit 0
fi

# If the original worker already moved everything, stop.
if [[ -f "$DEST/The Boondocks - S03E06.mkv" ]]; then
    log "Episodes already moved by original worker."
    exit 0
fi

log "Complete batch recovered. Waiting for validation lock."

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

log "===== CONTINUATION COMPLETE ====="
