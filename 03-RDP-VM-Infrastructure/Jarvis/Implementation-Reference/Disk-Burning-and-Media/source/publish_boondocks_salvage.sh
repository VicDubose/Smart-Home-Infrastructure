#!/usr/bin/env bash
set -euo pipefail

STAGE_ROOT="/mnt/appdata/jarvis-burner-staging/local-dvd"
LIBRARY="/mnt/media/Shows/The Boondocks/Season 03"
REPORT_ROOT="$HOME/Jarvis/reports/boondocks-publish"
STAMP="$(date +%Y%m%d-%H%M%S)"
REPORT="$REPORT_ROOT/publish-$STAMP.log"

EXPECTED=(
  "The Boondocks - S03E02 - Bitches to Rags.mkv"
  "The Boondocks - S03E04 - The Story of Jimmy Rebel.mkv"
  "The Boondocks - S03E07 - The Fund-Raiser.mkv"
  "The Boondocks - S03E09 - A Date with the Booty Warrior.mkv"
)

mkdir -p "$REPORT_ROOT"

exec > >(tee -a "$REPORT") 2>&1

echo "========================================================================"
echo " JARVIS — VALIDATE AND PUBLISH BOONDOCKS SALVAGE"
echo "========================================================================"
echo "Started: $(date)"
echo

STAGE="$(
    find "$STAGE_ROOT" \
      -mindepth 1 \
      -maxdepth 1 \
      -type d \
      -name 'boondocks-s03-salvage-*' \
      -printf '%T@ %p\n' 2>/dev/null |
    sort -nr |
    head -1 |
    cut -d' ' -f2-
)"

if [[ -z "$STAGE" || ! -d "$STAGE" ]]; then
    echo "BLOCK: No Boondocks salvage staging folder was found."
    exit 1
fi

ENCODED="$STAGE/encoded"

echo "Stage:   $STAGE"
echo "Library: $LIBRARY"
echo

if [[ ! -f "$STAGE/.encoding-complete" ]]; then
    echo "BLOCK: Salvage encoding did not finish successfully."
    echo
    journalctl --user \
      -u jarvis-boondocks-salvage \
      -n 100 \
      --no-pager || true
    exit 1
fi

COUNT="$(
    find "$ENCODED" \
      -maxdepth 1 \
      -type f \
      -name '*.mkv' |
    wc -l
)"

if [[ "$COUNT" -ne 4 ]]; then
    echo "BLOCK: Expected exactly four encoded episodes; found $COUNT."
    exit 1
fi

mkdir -p "$LIBRARY"

echo "===== VALIDATION ====="

for NAME in "${EXPECTED[@]}"
do
    SOURCE="$ENCODED/$NAME"
    DESTINATION="$LIBRARY/$NAME"
    CHECK_LOG="$REPORT_ROOT/${STAMP}-${NAME%.mkv}.decode.log"

    echo
    echo "------------------------------------------------------------------------"
    echo "$NAME"
    echo "------------------------------------------------------------------------"

    if [[ ! -s "$SOURCE" ]]; then
        echo "BLOCK: Required staged episode is missing or empty:"
        echo "$SOURCE"
        exit 1
    fi

    if [[ -e "$DESTINATION" ]]; then
        echo "BLOCK: Destination already exists:"
        echo "$DESTINATION"
        exit 1
    fi

    SIZE="$(stat -c '%s' "$SOURCE")"

    DURATION="$(
        ffprobe \
          -v error \
          -show_entries format=duration \
          -of default=nw=1:nk=1 \
          "$SOURCE"
    )"

    python3 - "$SIZE" "$DURATION" <<'PY'
import sys

size = int(sys.argv[1])
duration = float(sys.argv[2])

if size < 100_000_000:
    raise SystemExit(
        f"BLOCK: File is unexpectedly small: {size} bytes"
    )

if not 1200 <= duration <= 1500:
    raise SystemExit(
        f"BLOCK: Runtime is outside the expected "
        f"20–25 minute range: {duration:.3f} seconds"
    )

print(f"SIZE={size}")
print(f"DURATION={duration:.3f}")
PY

    STREAM_TYPES="$(
        ffprobe \
          -v error \
          -show_entries stream=codec_type \
          -of csv=p=0 \
          "$SOURCE"
    )"

    grep -qx video <<<"$STREAM_TYPES" || {
        echo "BLOCK: No video stream."
        exit 1
    }

    grep -qx audio <<<"$STREAM_TYPES" || {
        echo "BLOCK: No audio stream."
        exit 1
    }

    if ! timeout 30m ffmpeg \
        -nostdin \
        -hide_banner \
        -v warning \
        -xerror \
        -i "$SOURCE" \
        -map 0:v:0 \
        -map 0:a:0 \
        -f null - \
        </dev/null 2>"$CHECK_LOG"
    then
        echo "BLOCK: Full decode validation failed."
        tail -50 "$CHECK_LOG"
        exit 1
    fi

    DTS_WARNINGS="$(
        grep -c \
          'non monotonically increasing dts' \
          "$CHECK_LOG" 2>/dev/null ||
        true
    )"

    if [[ "$DTS_WARNINGS" -ne 0 ]]; then
        echo "BLOCK: Repaired output still has $DTS_WARNINGS DTS warnings."
        exit 1
    fi

    echo "FULL_DECODE=PASS"
    echo "DTS_WARNINGS=0"
done

echo
echo "===== ATOMIC JELLYFIN IMPORT ====="

for NAME in "${EXPECTED[@]}"
do
    SOURCE="$ENCODED/$NAME"
    DESTINATION="$LIBRARY/$NAME"
    PARTIAL="$LIBRARY/.jarvis-partial-${NAME}.$$"

    rm -f "$PARTIAL"

    echo
    echo "Copying: $NAME"

    cp \
      --reflink=auto \
      --sparse=always \
      "$SOURCE" \
      "$PARTIAL"

    SOURCE_HASH="$(sha256sum "$SOURCE" | awk '{print $1}')"
    COPY_HASH="$(sha256sum "$PARTIAL" | awk '{print $1}')"

    if [[ "$SOURCE_HASH" != "$COPY_HASH" ]]; then
        rm -f "$PARTIAL"
        echo "BLOCK: Copied file failed SHA-256 verification."
        exit 1
    fi

    chmod 0664 "$PARTIAL"
    mv "$PARTIAL" "$DESTINATION"

    echo "PUBLISHED=$DESTINATION"
done

touch "$STAGE/.published-to-jellyfin"
touch "$LIBRARY"

echo
echo "========================================================================"
echo " PASS: FOUR BOONDOCKS EPISODES PUBLISHED"
echo "========================================================================"

find "$LIBRARY" \
  -maxdepth 1 \
  -type f \
  \( \
    -name 'The Boondocks - S03E02 -*' \
    -o -name 'The Boondocks - S03E04 -*' \
    -o -name 'The Boondocks - S03E07 -*' \
    -o -name 'The Boondocks - S03E09 -*' \
  \) \
  -printf '%10s  %f\n' |
sort

echo
echo "Raw originals were preserved."
echo "Report: $REPORT"
