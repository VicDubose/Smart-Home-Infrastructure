#!/usr/bin/env bash
set -Eeuo pipefail

COOLDOWN_SECONDS=1200
NOW="$(date +%s)"

ARM_RAW="/mnt/appdata/arm/media/raw"
ARM_COMPLETED="/mnt/appdata/arm/media/completed"
ARM_JOBS="$HOME/Jarvis/jobs/arm-handoff"
ARM_STATE="$HOME/Jarvis/state/arm-handoff"

CALEB_WORKER="$HOME/rdp-scripts/Jarvis/media/jarvis_caleb_media_router.sh"

echo "========================================================================"
echo "JARVIS CALEB INGEST COOLDOWN GATE"
echo "========================================================================"

if [[ ! -f "$CALEB_WORKER" ]]; then
    echo "BLOCK: Caleb worker is missing: $CALEB_WORKER"
    exit 1
fi

echo
echo "===== ARM PROCESS CHECK ====="

if docker exec arm bash -lc \
    "pgrep -af '[/]opt/arm/arm/ripper/main\.py|[H]andBrakeCLI|[m]akemkvcon|[d]vdbackup|[f]fmpeg'" \
    >/tmp/jarvis-arm-active-processes.txt 2>/dev/null; then

    cat /tmp/jarvis-arm-active-processes.txt
    echo
    echo "WAIT: ARM is currently ripping or transcoding."
    echo "Caleb ingestion will be checked again on the next timer run."
    exit 0
fi

echo "PASS: ARM has no active ripping or transcoding processes."

echo
echo "===== RECENT ARM ACTIVITY CHECK ====="

LATEST_ACTIVITY="$(
    {
        find "$ARM_RAW" "$ARM_COMPLETED" \
            -type f \
            -iname '*.mkv' \
            -printf '%T@\n' \
            2>/dev/null || true

        find "$ARM_JOBS" \
            -type f \
            \( \
                -name 'validation_result.json' \
                -o -name 'handoff_manifest.json' \
                -o -name 'full_decode_report.txt' \
            \) \
            -printf '%T@\n' \
            2>/dev/null || true

        find "$ARM_STATE" \
            -maxdepth 1 \
            -type f \
            -name '*.json' \
            -printf '%T@\n' \
            2>/dev/null || true
    } |
    sort -nr |
    head -1 |
    cut -d. -f1
)"

if [[ -z "$LATEST_ACTIVITY" ]]; then
    echo "No previous ARM media activity was found."
    echo "PASS: No ARM cooldown is required."
else
    AGE_SECONDS=$(( NOW - LATEST_ACTIVITY ))
    REMAINING_SECONDS=$(( COOLDOWN_SECONDS - AGE_SECONDS ))

    echo "Newest meaningful ARM activity:"
    date -d "@$LATEST_ACTIVITY" '+%Y-%m-%d %H:%M:%S %Z'

    echo "Activity age: ${AGE_SECONDS} seconds"

    if (( AGE_SECONDS < COOLDOWN_SECONDS )); then
        REMAINING_MINUTES=$(( (REMAINING_SECONDS + 59) / 60 ))

        echo
        echo "WAIT: ARM or its Jarvis handoff finished recently."
        echo "Cooling time remaining: approximately ${REMAINING_MINUTES} minute(s)."
        echo "Caleb ingestion will be checked again automatically."
        exit 0
    fi

    echo "PASS: ARM has been idle for at least 20 minutes."
fi

echo
echo "===== STARTING CALEB RAW INGEST ====="
exec /usr/bin/bash "$CALEB_WORKER"
