#!/usr/bin/env bash

ARCHIVE_ROOT="/mnt/appdata/jarvis-pipeline-archives"
STATE_ROOT="$HOME/Jarvis/state/pipeline-archives"

echo
echo "===== JARVIS PIPELINE INSURANCE ARCHIVES ====="

if [[ ! -d "$ARCHIVE_ROOT" ]]; then
    echo "Status: archive root missing"
    echo "Path:   $ARCHIVE_ROOT"
    return 0 2>/dev/null || exit 0
fi

LATEST_DIR="$(
    find "$ARCHIVE_ROOT" \
      -mindepth 1 \
      -maxdepth 1 \
      -type d \
      -printf '%f\n' |
    sort -r |
    head -1
)"

ARCHIVE_COUNT="$(
    find "$ARCHIVE_ROOT" \
      -type f \
      -name '*.tar.gz' |
    wc -l
)"

TOTAL_SIZE="$(
    du -sh "$ARCHIVE_ROOT" 2>/dev/null |
    awk '{print $1}'
)"

echo "Archive root:       $ARCHIVE_ROOT"
echo "Compressed archives: $ARCHIVE_COUNT"
echo "Total archive size:  ${TOTAL_SIZE:-unknown}"
echo "Newest archive set:  ${LATEST_DIR:-none}"

if [[ -n "${LATEST_DIR:-}" ]]; then
    find "$ARCHIVE_ROOT/$LATEST_DIR" \
      -maxdepth 1 \
      -type f \
      \( -name '*.tar.gz' -o -name '*sha256*' \) \
      -printf '%TY-%Tm-%Td %TH:%TM  %10s bytes  %f\n' |
    sort
fi

if [[ -d "$STATE_ROOT" ]]; then
    printf "State records:       "
    find "$STATE_ROOT" \
      -maxdepth 1 \
      -type f \
      -name '*.json' |
    wc -l
fi
