#!/usr/bin/env bash
set -Eeuo pipefail

STAGE_ROOT="/mnt/appdata/jarvis-burner-staging/local-dvd"
LIBRARY="/mnt/media/Shows/The Boondocks/Season 03"
REPORT_ROOT="$HOME/Jarvis/reports/boondocks-publish"
STAMP="$(date +%Y%m%d-%H%M%S)"
REPORT="$REPORT_ROOT/manual-publish-$STAMP.log"

EXPECTED=(
  "The Boondocks - S03E02 - Bitches to Rags.mkv"
  "The Boondocks - S03E04 - The Story of Jimmy Rebel.mkv"
  "The Boondocks - S03E07 - The Fund-Raiser.mkv"
  "The Boondocks - S03E09 - A Date with the Booty Warrior.mkv"
)

mkdir -p "$REPORT_ROOT"
exec > >(tee -a "$REPORT") 2>&1

STAGE="$(
    find "$STAGE_ROOT" \
      -mindepth 1 \
      -maxdepth 1 \
      -type d \
      -name 'boondocks-s03-salvage-*' \
      -printf '%T@ %p\n' |
    sort -nr |
    head -1 |
    cut -d' ' -f2-
)"

[[ -n "$STAGE" && -d "$STAGE/encoded" ]] || {
    echo "BLOCK: Completed salvage stage was not found."
    exit 1
}

ENCODED="$STAGE/encoded"

echo "========================================================================"
echo " JARVIS — FINAL BOONDOCKS PUBLISH"
echo "========================================================================"
echo "Stage:   $STAGE"
echo "Library: $LIBRARY"
echo

echo "===== PRE-PUBLISH VALIDATION ====="

for NAME in "${EXPECTED[@]}"
do
    SOURCE="$ENCODED/$NAME"
    DESTINATION="$LIBRARY/$NAME"

    [[ -s "$SOURCE" ]] || {
        echo "BLOCK: Missing output: $SOURCE"
        exit 1
    }

    [[ ! -e "$DESTINATION" ]] || {
        echo "BLOCK: Destination already exists:"
        echo "$DESTINATION"
        exit 1
    }

    DURATION="$(
        ffprobe -v error \
          -show_entries format=duration \
          -of default=nw=1:nk=1 \
          "$SOURCE"
    )"

    python3 - "$DURATION" <<'PY'
import sys

try:
    duration = float(sys.argv[1])
except (IndexError, ValueError):
    raise SystemExit(1)

raise SystemExit(0 if 1200 <= duration <= 1500 else 1)
PY

    echo
    echo "$NAME"
    echo "SIZE=$(stat -c '%s' "$SOURCE")"
    echo "DURATION=$DURATION"

    ffmpeg \
      -nostdin \
      -hide_banner \
      -v error \
      -xerror \
      -i "$SOURCE" \
      -map 0:v:0 \
      -map 0:a:0 \
      -f null -

    echo "FULL_DECODE=PASS"
done

echo
echo "===== SAFE COPY TO JELLYFIN ====="

mkdir -p "$LIBRARY"

PARTIALS=()

cleanup_partials() {
    for FILE in "${PARTIALS[@]:-}"
    do
        rm -f -- "$FILE"
    done
}

trap cleanup_partials ERR INT TERM

for NAME in "${EXPECTED[@]}"
do
    SOURCE="$ENCODED/$NAME"
    PARTIAL="$LIBRARY/.${NAME}.jarvis-partial"

    [[ ! -e "$PARTIAL" ]] || {
        echo "BLOCK: Temporary destination already exists:"
        echo "$PARTIAL"
        exit 1
    }

    PARTIALS+=("$PARTIAL")

    cp --reflink=auto --preserve=timestamps \
      "$SOURCE" \
      "$PARTIAL"

    SOURCE_HASH="$(sha256sum "$SOURCE" | awk '{print $1}')"
    PARTIAL_HASH="$(sha256sum "$PARTIAL" | awk '{print $1}')"

    [[ "$SOURCE_HASH" == "$PARTIAL_HASH" ]] || {
        echo "BLOCK: Copy verification failed for $NAME"
        exit 1
    }

    echo "COPY_VERIFIED: $NAME"
done

for NAME in "${EXPECTED[@]}"
do
    PARTIAL="$LIBRARY/.${NAME}.jarvis-partial"
    DESTINATION="$LIBRARY/$NAME"

    # Hard-link creation fails rather than overwriting an existing file.
    ln "$PARTIAL" "$DESTINATION"
    rm "$PARTIAL"

    echo "PUBLISHED: $DESTINATION"
done

PARTIALS=()
trap - ERR INT TERM

touch "$STAGE/.published"
sync -f "$LIBRARY" 2>/dev/null || true

echo
echo "========================================================================"
echo " PASS: FOUR BOONDOCKS EPISODES PUBLISHED"
echo "========================================================================"

find "$LIBRARY" \
  -maxdepth 1 \
  -type f \
  -name 'The Boondocks - S03E*.mkv' \
  -printf '%10s  %f\n' |
sort

echo
echo "Report: $REPORT"
