#!/usr/bin/env bash
set -Eeuo pipefail

DEVICE="/dev/sr0"
SHOW="The Boondocks"
SEASON=3
DEST="/mnt/media/Shows/The Boondocks/Season 03"
PIPE="$HOME/rdp-scripts/Jarvis/media/jarvis_disc_ingest_guarded_v2.py"
VALIDATOR="$HOME/rdp-scripts/Jarvis/media/jarvis_validate_rip.py"
MOVER="$HOME/rdp-scripts/Jarvis/media/jarvis_move_if_valid.py"

STAMP="$(date +%Y%m%d-%H%M%S)"
STAGE="$HOME/rips/boondocks-s3d2-final-$STAMP"
FAILED="$STAGE/failed-attempts"
RESULT="$STAGE/validation_result.json"
STATE="$HOME/rips/reports/boondocks-s3d2-last-staging.txt"
LOCK="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/jarvis-media-ingest.lock"

mkdir -p "$STAGE" "$FAILED" "$HOME/rips/reports"
printf '%s\n' "$STAGE" > "$STATE"

log() {
    printf '[%s] %s\n' "$(date '+%F %T')" "$*"
}

valid_episode() {
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

# Boondocks episodes on this disc are roughly 21:48–22:36.
# Give enough margin for container/authoring differences while rejecting
# the previous 18:52 truncated failure.
raise SystemExit(0 if 1200 <= d <= 1500 else 1)
PY
}

pipeline_rip() {
    local title="$1"
    local output="$2"

    log "Starting DVD Title $title -> $(basename "$output")"

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
    "jarvis_guarded_v2_exception",
    pipeline,
)

module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

try:
    module.rip_title(device, title, output)
except SystemExit as exc:
    code = exc.code
    if not isinstance(code, int):
        code = 1
    raise SystemExit(code)
PY
}

rip_episode() {
    local episode="$1"
    shift

    local output="$STAGE/The Boondocks - S03E${episode}.mkv"

    for title in "$@"; do
        log "Trying S03E${episode} using DVD Title $title"

        if pipeline_rip "$title" "$output"; then
            if valid_episode "$output"; then
                log "PASS: S03E${episode} from Title $title"
                return 0
            fi

            log "FAIL: Title $title returned an invalid runtime."
        else
            log "FAIL: HandBrake/pipeline failed for Title $title."
        fi

        if [[ -f "$output" ]]; then
            mv \
              "$output" \
              "$FAILED/S03E${episode}-title-${title}-failed.mkv"
        fi

        log "Trying fallback title for S03E${episode}."
    done

    log "FATAL: all title paths failed for S03E${episode}."
    return 1
}

seed_episode() {
    local source="$1"
    local episode="$2"
    local output="$STAGE/The Boondocks - S03E${episode}.mkv"

    if valid_episode "$source"; then
        log "Reusing already-good decoded video for S03E${episode}: $source"

        cp \
          --reflink=auto \
          --preserve=timestamps \
          "$source" \
          "$output"

        return 0
    fi

    return 1
}


###############################################################################
# SAFETY PRECHECK
###############################################################################

log "===== BOONDOCKS S3D2 KNOWN-DISC EXCEPTION ====="
log "Staging: $STAGE"

if [[ ! -b "$DEVICE" ]]; then
    log "BLOCK: $DEVICE does not exist."
    exit 1
fi

LABEL="$(lsblk -ndo LABEL "$DEVICE" 2>/dev/null | xargs || true)"

log "Detected label: ${LABEL:-none}"

if [[ "$LABEL" != *"BOONDOCKS_S3_D2"* ]]; then
    log "BLOCK: unexpected disc in $DEVICE."
    exit 1
fi

if ! lsdvd -x -t 1 "$DEVICE" 2>/dev/null |
     grep -q 'Disc Title: BOONDOCKS_S3_D2'; then
    log "BLOCK: DVD structure does not identify as BOONDOCKS_S3_D2."
    exit 1
fi

if pgrep -af \
   'HandBrakeCLI.*(/dev/sr0|sr0)|jarvis_disc_ingest_guarded_v2.py.*--device /dev/sr0' \
   >"$STAGE/preexisting-processes.txt"; then

    log "BLOCK: another SR0 rip process is already active."
    cat "$STAGE/preexisting-processes.txt"
    exit 1
fi

if [[ -d "$DEST" ]]; then
    for ep in 06 07 08 09 10; do
        if find "$DEST" \
             -maxdepth 1 \
             -type f \
             -iname "*S03E${ep}*.mkv" \
             -print -quit |
           grep -q .; then

            log "BLOCK: S03E${ep} already exists in Jellyfin."
            exit 1
        fi
    done
fi


###############################################################################
# REUSE THE TWO GOOD RIPS WE ALREADY PAID THE TIME FOR
###############################################################################

# Existing S03E06 was actually DVD Title 1 = real S03E07 Fund-Raiser.
if ! seed_episode \
     "$HOME/rips/staging/The Boondocks - S03E06.mkv" \
     07; then

    log "Existing Title-1 rip unavailable; reripping E07."
    rip_episode 07 1 3
fi

# Existing S03E07 was DVD Title 2 = real S03E09.
if ! seed_episode \
     "$HOME/rips/staging/The Boondocks - S03E07.mkv" \
     09; then

    log "Existing Title-2 rip unavailable; reripping E09."
    rip_episode 09 2 4
fi


###############################################################################
# RIP THE THREE EPISODES WE ACTUALLY STILL NEED
###############################################################################

# E06: prefer Title 7 because Title 5 previously died near 86.8%.
rip_episode 06 7 5

# E08: Pause.
rip_episode 08 29 30

# E10: prefer Title 6 because Title 8 showed dvdnav read trouble.
rip_episode 10 6 8


###############################################################################
# FINAL LOCAL PRECHECK
###############################################################################

log "===== FIVE-EPISODE STAGING CHECK ====="

for ep in 06 07 08 09 10; do
    f="$STAGE/The Boondocks - S03E${ep}.mkv"

    if ! valid_episode "$f"; then
        log "BLOCK: S03E${ep} failed final local runtime check."
        exit 1
    fi

    ffprobe \
      -v error \
      -show_entries format=duration,size \
      -of default=noprint_wrappers=1 \
      "$f"
done


###############################################################################
# ONE SHARED JARVIS VALIDATION / MOVE WINDOW
###############################################################################

log "Waiting for Jarvis validation lock."

exec 8>"$LOCK"
flock 8

log "Validation lock acquired."

python3 "$VALIDATOR" \
  --show "$SHOW" \
  --season "$SEASON" \
  --start 6 \
  --end 10 \
  --staging "$STAGE" \
  --write-result "$RESULT" \
  --ai llama3.2:3b

python3 "$MOVER" \
  --validation "$RESULT" \
  --destination "$DEST"

flock -u 8

log "===== BOONDOCKS S3D2 COMPLETE ====="
log "Validation passed and move gate completed."
log "Destination: $DEST"
