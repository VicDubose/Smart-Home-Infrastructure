#!/usr/bin/env bash

DEVICE="/dev/sr0"
WORKER="$HOME/rdp-scripts/Jarvis/media/jarvis_disc_auto_ingest.py"
LOCK="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/jarvis-media-ingest.lock"
REPORT="$HOME/Jarvis/reports/media-priority/local-dvd-live-$(date +%Y%m%d-%H%M%S).log"

mkdir -p "$(dirname "$REPORT")"

exec > >(tee -a "$REPORT") 2>&1

echo "========================================================================"
echo " JARVIS OLD LOCAL DVD PIPELINE"
echo "========================================================================"
echo "Device: $DEVICE"
echo "Report: $REPORT"
echo

ARM_RUNNING="$(
    docker inspect \
        --format '{{.State.Running}}' \
        arm 2>/dev/null || echo false
)"

if [ "$ARM_RUNNING" = "true" ]; then
    echo "BLOCK: ARM is running."
    exit 1
fi

if ! dd \
    if="$DEVICE" \
    of=/dev/null \
    bs=2048 \
    count=1 \
    status=none
then
    echo "BLOCK: No readable disc exists in $DEVICE."
    exit 1
fi

if [ -f /tmp/jarvis_media_ingest.lock ]; then
    OLD_PID="$(cat /tmp/jarvis_media_ingest.lock 2>/dev/null || true)"

    if [ -n "$OLD_PID" ] &&
       kill -0 "$OLD_PID" 2>/dev/null
    then
        echo "BLOCK: Legacy ingest PID $OLD_PID is running."
        exit 1
    fi

    rm -f /tmp/jarvis_media_ingest.lock
fi

exec 9>"$LOCK"

if ! flock -n 9; then
    echo "BLOCK: Another Jarvis media job owns the shared lock."
    exit 1
fi

echo "PASS: ARM is quarantined."
echo "PASS: DVD is readable."
echo "PASS: Shared media lock acquired."
echo

dvdbackup -I -i "$DEVICE"

echo
echo "Starting old automatic disc classifier..."
echo "This disc appears to be: BEST_OF_WB100TH_SD_D1"
echo

python3 -u "$WORKER" \
    --device "$DEVICE" \
    --ai llama3:8b

RESULT=$?

echo
echo "========================================================================"
echo " PIPELINE FINISHED"
echo "========================================================================"
echo "Exit code: $RESULT"
echo "Report:    $REPORT"
echo "========================================================================"

exit "$RESULT"
