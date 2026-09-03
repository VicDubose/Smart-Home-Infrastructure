#!/usr/bin/env bash
#
# Jarvis central media-priority cycle
#
# Order:
#   1. Register newly completed local ARM movies
#   2. Register newly eligible Caleb remote sources
#   3. Dispatch at most one READY validation job
#   4. Check for successfully validated discs eligible for safe ejection
#
# Only the dispatcher exit code controls the final service result.
#

set -u
set -o pipefail

HOME_ROOT="/home/onsiteadmin"
MEDIA_ROOT="$HOME_ROOT/rdp-scripts/Jarvis/media"

ARM_REGISTRAR="$MEDIA_ROOT/jarvis_arm_movie_registrar.py"
CALEB_REGISTRAR="$MEDIA_ROOT/jarvis_caleb_registrar.py"
DISPATCHER="$MEDIA_ROOT/jarvis_media_priority_dispatcher.py"
SAFE_EJECT="$MEDIA_ROOT/jarvis_safe_eject.py"

LOG_ROOT="$HOME_ROOT/Jarvis/logs/media-priority"
RUNTIME_DIR="/run/user/$(id -u)"

STAMP="$(date '+%Y%m%d-%H%M%S')"
LOG_FILE="$LOG_ROOT/master-cycle-$STAMP.log"
LATEST_LOG="$LOG_ROOT/latest.log"
CYCLE_LOCK="$RUNTIME_DIR/jarvis-media-priority-cycle.lock"

mkdir -p "$LOG_ROOT" "$RUNTIME_DIR"

exec 9>"$CYCLE_LOCK"

if ! flock -n 9; then
    echo "WAIT: Another Jarvis master cycle is already running."
    exit 0
fi

exec > >(tee -a "$LOG_FILE") 2>&1

finish_log() {
    echo
    echo "Completed: $(date)"
    echo "Log:       $LOG_FILE"
    echo "========================================================================"

    ln -sfn "$LOG_FILE" "$LATEST_LOG"
}

echo "========================================================================"
echo " JARVIS MASTER MEDIA-PRIORITY CYCLE"
echo "========================================================================"
echo "Started: $(date)"
echo "PID:     $$"
echo

echo "------------------------------------------------------------------------"
echo "0. VERIFY REQUIRED PIPELINE COMPONENTS"
echo "------------------------------------------------------------------------"

REQUIRED_FAILURE=0

for REQUIRED_FILE in \
    "$ARM_REGISTRAR" \
    "$CALEB_REGISTRAR" \
    "$DISPATCHER"
do
    if [ ! -f "$REQUIRED_FILE" ]; then
        echo "BLOCK: Required pipeline component is missing:"
        echo "$REQUIRED_FILE"
        REQUIRED_FAILURE=1
    else
        echo "PASS: $REQUIRED_FILE"
    fi
done

if [ "$REQUIRED_FAILURE" -ne 0 ]; then
    echo
    echo "BLOCK: One or more required pipeline components are missing."
    finish_log
    exit 1
fi

echo
echo "------------------------------------------------------------------------"
echo "1. REGISTER NEWLY COMPLETED ARM MOVIES"
echo "------------------------------------------------------------------------"

python3 -u "$ARM_REGISTRAR"
ARM_REGISTRAR_RESULT=$?

echo
echo "ARM registrar exit code: $ARM_REGISTRAR_RESULT"

if [ "$ARM_REGISTRAR_RESULT" -ne 0 ]; then
    echo "BLOCK: ARM movie registration failed."
    echo "Dispatch will not run during this cycle."
    finish_log
    exit "$ARM_REGISTRAR_RESULT"
fi

echo
echo "------------------------------------------------------------------------"
echo "2. REGISTER NEWLY ELIGIBLE CALEB SOURCES"
echo "------------------------------------------------------------------------"

python3 -u "$CALEB_REGISTRAR" --commit
CALEB_REGISTRAR_RESULT=$?

echo
echo "Caleb registrar exit code: $CALEB_REGISTRAR_RESULT"

if [ "$CALEB_REGISTRAR_RESULT" -ne 0 ]; then
    echo "BLOCK: Caleb source registration failed."
    echo "Dispatch will not run during this cycle."
    finish_log
    exit "$CALEB_REGISTRAR_RESULT"
fi

echo
echo "------------------------------------------------------------------------"
echo "3. DISPATCH AT MOST ONE READY JOB"
echo "------------------------------------------------------------------------"

python3 -u "$DISPATCHER" --execute
DISPATCH_RESULT=$?

echo
echo "Dispatcher exit code: $DISPATCH_RESULT"

echo
echo "------------------------------------------------------------------------"
echo "4. CHECK FOR DISCS ELIGIBLE FOR SAFE EJECTION"
echo "------------------------------------------------------------------------"

if [ -f "$SAFE_EJECT" ]; then
    python3 -u "$SAFE_EJECT"
    SAFE_EJECT_RESULT=$?

    echo
    echo "Safe-eject exit code: $SAFE_EJECT_RESULT"

    if [ "$SAFE_EJECT_RESULT" -ne 0 ]; then
        echo "WARNING: Safe-eject check failed."
        echo "This does not change the validation result."
    fi
else
    echo "SKIP: Safe-eject script is not installed:"
    echo "$SAFE_EJECT"
fi

finish_log

exit "$DISPATCH_RESULT"
