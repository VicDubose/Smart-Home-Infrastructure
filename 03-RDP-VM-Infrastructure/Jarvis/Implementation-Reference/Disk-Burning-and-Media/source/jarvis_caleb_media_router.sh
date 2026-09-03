#!/usr/bin/env bash
set -Eeuo pipefail

HOME_DIR="/home/onsiteadmin"
MEDIA_DIR="$HOME_DIR/rdp-scripts/Jarvis/media"

TV_WORKER="$MEDIA_DIR/jarvis_caleb_queue_worker.py"
MOVIE_WORKER="$MEDIA_DIR/jarvis_caleb_movie_worker.py"

echo "========================================================================"
echo "JARVIS CALEB MEDIA ROUTER"
echo "========================================================================"

if [[ ! -f "$TV_WORKER" ]]; then
    echo "BLOCK: TV worker is missing: $TV_WORKER"
    exit 1
fi

if [[ ! -f "$MOVIE_WORKER" ]]; then
    echo "BLOCK: Movie worker is missing: $MOVIE_WORKER"
    exit 1
fi

echo
echo "===== TV INGEST PATH ====="

TV_RESULT=0
/usr/bin/python3 -u "$TV_WORKER" || TV_RESULT=$?

echo
echo "TV worker return code: $TV_RESULT"

echo
echo "===== MOVIE INGEST PATH ====="

MOVIE_RESULT=0
/usr/bin/python3 -u "$MOVIE_WORKER" || MOVIE_RESULT=$?

echo
echo "Movie worker return code: $MOVIE_RESULT"

echo
echo "===== ROUTER SUMMARY ====="
echo "TV:     $TV_RESULT"
echo "Movies: $MOVIE_RESULT"

# A review/block result from one media type should be logged but should not
# prevent the timer from running again. Hard prerequisites are handled above.
exit 0
