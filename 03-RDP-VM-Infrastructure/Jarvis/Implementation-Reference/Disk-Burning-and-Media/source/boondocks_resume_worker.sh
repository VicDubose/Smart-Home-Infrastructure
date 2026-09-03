#!/usr/bin/env bash

DEVICE="$1"
STAGE="$2"

for TITLE in 2 3 4 5 6 7 8; do
    EPISODE="$(printf '%02d' "$TITLE")"
    OUTPUT="$STAGE/The Boondocks - S03E${EPISODE}.mkv"
    TEMP="${OUTPUT}.partial"

    rm -f "$TEMP"

    echo
    echo "============================================================"
    echo "Ripping title $TITLE as S03E${EPISODE}"
    echo "============================================================"

    HandBrakeCLI \
        -i "$DEVICE" \
        -t "$TITLE" \
        -o "$TEMP" \
        --format av_mkv \
        -e x264 \
        -q 19 \
        -B 160

    RC=$?

    if [ "$RC" -ne 0 ] || [ ! -s "$TEMP" ]; then
        echo "BLOCK: Title $TITLE failed with exit code $RC."
        exit 1
    fi

    DURATION="$(
        ffprobe -v error \
            -show_entries format=duration \
            -of default=noprint_wrappers=1:nokey=1 \
            "$TEMP"
    )"

    python3 - "$DURATION" <<'PY'
import sys

duration = float(sys.argv[1])
if not 1200 <= duration <= 1500:
    raise SystemExit(1)
PY

    if [ "$?" -ne 0 ]; then
        echo "BLOCK: Title $TITLE has invalid duration: $DURATION seconds."
        exit 1
    fi

    mv "$TEMP" "$OUTPUT"
    echo "PASS: S03E${EPISODE} completed."
done

echo
echo "CAPTURE COMPLETE: Episodes 1–8 are staged."
