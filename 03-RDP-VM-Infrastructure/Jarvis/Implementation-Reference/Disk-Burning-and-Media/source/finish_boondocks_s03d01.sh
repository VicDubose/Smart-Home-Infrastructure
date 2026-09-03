#!/usr/bin/env bash

LOCK="/tmp/jarvis-boondocks-s03d01.lock"
RAW_ROOT="/mnt/appdata/jarvis-burner-staging/local-dvd-raw"
ENCODE_ROOT="/mnt/appdata/jarvis-burner-staging/local-dvd"
LIBRARY="/mnt/media/Shows/The Boondocks/Season 03"
LOG_ROOT="$HOME/Jarvis/logs/media-priority"

mkdir -p "$LOG_ROOT"

exec 9>"$LOCK"
if ! flock -n 9; then
    echo "BLOCK: Another Boondocks finishing job is already running."
    exit 1
fi

echo "============================================================"
echo " JARVIS — FINISH BOONDOCKS SEASON 3 DISC 1"
echo "============================================================"

echo
echo "Waiting for the raw DVD copy to finish..."

while pgrep -af '[d]vdbackup.*Boondocks-S03D01' >/dev/null; do
    sleep 30
done

RAW_JOB="$(
    find "$RAW_ROOT" \
        -maxdepth 1 \
        -mindepth 1 \
        -type d \
        -name 'Boondocks-S03D01-*' \
        -printf '%T@ %p\n' 2>/dev/null |
    sort -nr |
    head -1 |
    cut -d' ' -f2-
)"

if [ -z "$RAW_JOB" ] || [ ! -d "$RAW_JOB" ]; then
    echo "BLOCK: No completed Boondocks raw-copy folder was found."
    exit 1
fi

VIDEO_TS="$(
    find "$RAW_JOB" \
        -type d \
        -iname VIDEO_TS \
        -print \
        -quit
)"

if [ -z "$VIDEO_TS" ] || [ ! -d "$VIDEO_TS" ]; then
    echo "BLOCK: VIDEO_TS was not found inside:"
    echo "$RAW_JOB"
    exit 1
fi

VOB_COUNT="$(find "$VIDEO_TS" -maxdepth 1 -type f -iname '*.VOB' | wc -l)"

if [ "$VOB_COUNT" -lt 8 ]; then
    echo "BLOCK: Raw copy appears incomplete. VOB files found: $VOB_COUNT"
    exit 1
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
STAGE="$ENCODE_ROOT/Boondocks-S03D01-final-$STAMP"

mkdir -p "$STAGE"

echo
echo "Raw source: $RAW_JOB"
echo "VIDEO_TS:   $VIDEO_TS"
echo "Staging:    $STAGE"
echo

for TITLE in 1 2 3 4 5 6 7 8; do
    EPISODE="$(printf '%02d' "$TITLE")"
    FINAL="$STAGE/The Boondocks - S03E${EPISODE}.mkv"
    PARTIAL="${FINAL}.partial"

    echo "============================================================"
    echo "Encoding DVD title $TITLE as S03E${EPISODE}"
    echo "============================================================"

    SUCCESS=0

    for ATTEMPT in 1 2 3; do
        rm -f "$PARTIAL"

        echo "Attempt $ATTEMPT of 3"

        HandBrakeCLI \
            -i "$VIDEO_TS" \
            -t "$TITLE" \
            -o "$PARTIAL" \
            --format av_mkv \
            -e x264 \
            -q 19 \
            -B 160

        RC=$?

        if [ "$RC" -ne 0 ] || [ ! -s "$PARTIAL" ]; then
            echo "Attempt $ATTEMPT failed during encoding."
            sleep 10
            continue
        fi

        DURATION="$(
            ffprobe \
                -v error \
                -show_entries format=duration \
                -of default=noprint_wrappers=1:nokey=1 \
                "$PARTIAL" 2>/dev/null
        )"

        if ! python3 - "$DURATION" <<'PY'
import sys

try:
    duration = float(sys.argv[1])
except (IndexError, ValueError):
    raise SystemExit(1)

raise SystemExit(0 if 1200 <= duration <= 1500 else 1)
PY
        then
            echo "Attempt $ATTEMPT produced an invalid duration: ${DURATION:-unknown}"
            sleep 10
            continue
        fi

        if ! ffmpeg \
            -hide_banner \
            -v error \
            -xerror \
            -i "$PARTIAL" \
            -map 0:v:0 \
            -map 0:a:0 \
            -f null -; then
            echo "Attempt $ATTEMPT failed the full decode validation."
            sleep 10
            continue
        fi

        mv "$PARTIAL" "$FINAL"

        echo "PASS: S03E${EPISODE}"
        echo "Duration: $DURATION seconds"
        SUCCESS=1
        break
    done

    if [ "$SUCCESS" -ne 1 ]; then
        echo
        echo "BLOCK: S03E${EPISODE} failed all three attempts."
        echo "Nothing was moved into Jellyfin."
        exit 1
    fi
done

COUNT="$(find "$STAGE" -maxdepth 1 -type f -name '*.mkv' | wc -l)"

if [ "$COUNT" -ne 8 ]; then
    echo "BLOCK: Expected 8 validated episodes but found $COUNT."
    exit 1
fi

mkdir -p "$LIBRARY"

for FILE in "$STAGE"/*.mkv; do
    DESTINATION="$LIBRARY/$(basename "$FILE")"

    if [ -e "$DESTINATION" ]; then
        echo "BLOCK: A destination file already exists:"
        echo "$DESTINATION"
        exit 1
    fi
done

echo
echo "All eight episodes passed. Importing into Jellyfin..."

for FILE in "$STAGE"/*.mkv; do
    mv "$FILE" "$LIBRARY/"
done

touch "$STAGE/.passed"

echo
echo "============================================================"
echo " PASS: BOONDOCKS SEASON 3 DISC 1 COMPLETE"
echo "============================================================"
echo "Imported into:"
echo "$LIBRARY"
echo
find "$LIBRARY" \
    -maxdepth 1 \
    -type f \
    -name 'The Boondocks - S03E0[1-8].mkv' \
    -printf '%10s  %f\n' |
sort
