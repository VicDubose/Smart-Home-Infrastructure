#!/usr/bin/env bash
set -euo pipefail

RAW="/mnt/appdata/arm/media/raw"
STAGE_ROOT="/mnt/appdata/jarvis-burner-staging/local-dvd"
STAMP="$(date +%Y%m%d-%H%M%S)"
STAGE="$STAGE_ROOT/boondocks-s03-salvage-$STAMP"
ENCODED="$STAGE/encoded"
REPORTS="$STAGE/reports"
MAPPING="$STAGE/source-map.tsv"

mkdir -p "$ENCODED" "$REPORTS"

SOURCES=(
  "$RAW/The Boondocks S3D1/title_t00.mkv"
  "$RAW/The Boondocks S3D1/title_t01.mkv"
  "$RAW/The Boondocks/title_t00.mkv"
  "$RAW/The Boondocks/title_t01.mkv"
)

NAMES=(
  "The Boondocks - S03E02 - Bitches to Rags.mkv"
  "The Boondocks - S03E04 - The Story of Jimmy Rebel.mkv"
  "The Boondocks - S03E07 - The Fund-Raiser.mkv"
  "The Boondocks - S03E09 - A Date with the Booty Warrior.mkv"
)

echo "========================================================================"
echo " JARVIS — BOONDOCKS SEASON 3 SALVAGE"
echo "========================================================================"
echo "Staging: $STAGE"

printf 'source\toutput\n' > "$MAPPING"

for INDEX in "${!SOURCES[@]}"
do
    SOURCE="${SOURCES[$INDEX]}"
    NAME="${NAMES[$INDEX]}"
    FINAL="$ENCODED/$NAME"
    PARTIAL="$FINAL.partial.mkv"
    LOG="$REPORTS/${NAME%.mkv}.encode.log"
    DECODE_LOG="$REPORTS/${NAME%.mkv}.decode.log"

    echo
    echo "------------------------------------------------------------------------"
    echo "$NAME"
    echo "Source: $SOURCE"
    echo "------------------------------------------------------------------------"

    if [[ ! -s "$SOURCE" ]]; then
        echo "BLOCK: Source is missing or empty."
        exit 1
    fi

    if [[ -e "$FINAL" || -e "$PARTIAL" ]]; then
        echo "BLOCK: Staging destination already exists."
        exit 1
    fi

    SOURCE_DURATION="$(
        ffprobe -v error \
          -show_entries format=duration \
          -of default=nw=1:nk=1 \
          "$SOURCE"
    )"

    RATE="$(
        ffprobe -v error \
          -select_streams v:0 \
          -show_entries stream=avg_frame_rate \
          -of default=nw=1:nk=1 \
          "$SOURCE"
    )"

    if [[ -z "$RATE" || "$RATE" == "0/0" ]]; then
        RATE="30000/1001"
    fi

    echo "Frame rate:      $RATE"
    echo "Source duration: $SOURCE_DURATION"

    ffmpeg \
      -nostdin \
      -hide_banner \
      -y \
      -fflags +genpts \
      -i "$SOURCE" \
      -map 0:v:0 \
      -map 0:a:0 \
      -map '0:s?' \
      -vf "setpts=N/($RATE*TB)" \
      -af "aresample=async=1:first_pts=0" \
      -c:v libx264 \
      -preset medium \
      -crf 19 \
      -pix_fmt yuv420p \
      -c:a aac \
      -b:a 160k \
      -c:s srt \
      -metadata title="${NAME%.mkv}" \
      -max_muxing_queue_size 4096 \
      "$PARTIAL" \
      >"$LOG" 2>&1

    if [[ ! -s "$PARTIAL" ]]; then
        echo "BLOCK: Encoder did not produce an output."
        exit 1
    fi

    OUTPUT_DURATION="$(
        ffprobe -v error \
          -show_entries format=duration \
          -of default=nw=1:nk=1 \
          "$PARTIAL"
    )"

    python3 - "$SOURCE_DURATION" "$OUTPUT_DURATION" <<'PY'
import sys

source = float(sys.argv[1])
output = float(sys.argv[2])
difference = abs(source - output)

print(f"Output duration: {output:.3f}")
print(f"Duration difference: {difference:.3f}")

if difference > 5:
    raise SystemExit("BLOCK: Output duration differs by more than five seconds.")
PY

    STREAMS="$(
        ffprobe -v error \
          -show_entries stream=codec_type \
          -of csv=p=0 \
          "$PARTIAL"
    )"

    grep -qx video <<<"$STREAMS" || {
        echo "BLOCK: Output has no video stream."
        exit 1
    }

    grep -qx audio <<<"$STREAMS" || {
        echo "BLOCK: Output has no audio stream."
        exit 1
    }

    if ! timeout 30m ffmpeg \
        -nostdin \
        -hide_banner \
        -v warning \
        -xerror \
        -i "$PARTIAL" \
        -map 0:v:0 \
        -map 0:a:0 \
        -f null - \
        </dev/null 2>"$DECODE_LOG"
    then
        echo "BLOCK: Full decode validation failed."
        tail -40 "$DECODE_LOG"
        exit 1
    fi

    DTS_WARNINGS="$(
        grep -c \
          'non monotonically increasing dts' \
          "$DECODE_LOG" 2>/dev/null ||
        true
    )"

    if [[ "$DTS_WARNINGS" -ne 0 ]]; then
        echo "BLOCK: Normalized file still has DTS warnings: $DTS_WARNINGS"
        exit 1
    fi

    mv "$PARTIAL" "$FINAL"

    printf '%s\t%s\n' "$SOURCE" "$FINAL" >> "$MAPPING"

    echo "PASS: $NAME"
    du -h "$FINAL"
done

touch "$STAGE/.encoding-complete"

echo
echo "========================================================================"
echo " PASS: FOUR CLEAN EPISODES STAGED"
echo "========================================================================"
echo "STAGE=$STAGE"
echo
find "$ENCODED" \
  -maxdepth 1 \
  -type f \
  -name '*.mkv' \
  -printf '%10s  %f\n' |
sort
