#!/usr/bin/env bash
set -euo pipefail

SYNC_SCRIPT="$HOME/rdp-scripts/Jarvis/media/jarvis_reverse_library_sync.py"
LOG_DIR="$HOME/Jarvis/logs/reverse-sync"
LOG="$LOG_DIR/idle-wait-$(date +%Y%m%d-%H%M%S).log"

mkdir -p "$LOG_DIR"

# Friday VPN window ends at 10:00 AM.
# The service begins at 1:15 AM, giving it up to 8 hours 30 minutes.
MAX_WAIT_SECONDS=$((8 * 3600 + 30 * 60))
CHECK_INTERVAL=300
WAITED=0

BUSY_PATTERN='HandBrakeCLI|ffmpeg|dvdbackup|makemkv|rsync|jarvis_disc_auto_ingest|jarvis_disc_ingest_guarded|jarvis_caleb_queue_worker|process_caleb'

{
    echo "========================================================================"
    echo "REVERSE SYNC IDLE WAIT"
    echo "Started: $(date --iso-8601=seconds)"
    echo "========================================================================"

    while true; do
        ACTIVE="$(
            pgrep -af "$BUSY_PATTERN" |
            grep -vE 'pgrep|run_reverse_sync_when_idle|jarvis_reverse_library_sync' \
            || true
        )"

        if [ -z "$ACTIVE" ]; then
            echo "Jarvis is idle."
            echo "Starting reverse-library sync."
            exec "$SYNC_SCRIPT"
        fi

        echo
        echo "Jarvis is busy:"
        echo "$ACTIVE"

        if [ "$WAITED" -ge "$MAX_WAIT_SECONDS" ]; then
            echo
            echo "Maintenance window expired."
            echo "Reverse sync will wait until next Friday."
            exit 0
        fi

        echo "Checking again in 5 minutes."
        sleep "$CHECK_INTERVAL"
        WAITED=$((WAITED + CHECK_INTERVAL))
    done
} 2>&1 | tee -a "$LOG"
