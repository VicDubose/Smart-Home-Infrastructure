#!/usr/bin/env bash

set -u

ROOT="/mnt/appdata/ha-services/local-events"
DB="$ROOT/data/local_events.db"
PY="$ROOT/.venv/bin/python"
LOGDIR="$ROOT/logs"
STATE="$ROOT/state"

# Thermal policy
START_TEMP=75
HARD_PAUSE_TEMP=88
CHECK_SECONDS=30
COOLDOWN_MIN_SECONDS=600
MAX_COOLDOWN_SECONDS=3600

mkdir -p "$LOGDIR" "$STATE"

cd "$ROOT" || exit 1


###############################################################################
# HELPERS
###############################################################################

get_temp() {
    sensors 2>/dev/null \
    | awk '
        /^Tctl:/ {
            gsub(/[+°C]/, "", $2)
            print int($2)
            exit
        }
    '
}


pending_jobs() {
    sqlite3 "$DB" "
        SELECT COUNT(*)
        FROM ai_jobs
        WHERE status = 'pending';
    " 2>/dev/null
}


processing_jobs() {
    sqlite3 "$DB" "
        SELECT COUNT(*)
        FROM ai_jobs
        WHERE status = 'processing';
    " 2>/dev/null
}


queue_report() {
    sqlite3 -header -column "$DB" '
        SELECT
            status,
            COUNT(*) AS jobs
        FROM ai_jobs
        GROUP BY status
        ORDER BY status;
    '
}


unload_ollama() {
    echo "Unloading Ollama models..."

    ollama ps 2>/dev/null \
    | awk 'NR > 1 {print $1}' \
    | while read -r model; do
        [ -n "$model" ] || continue
        echo "  ollama stop $model"
        ollama stop "$model" >/dev/null 2>&1 || true
    done
}


stop_worker() {
    local pid="${1:-}"

    [ -n "$pid" ] || return 0

    if kill -0 "$pid" 2>/dev/null; then

        echo "Stopping AI worker PID $pid gracefully..."

        kill -TERM "$pid" 2>/dev/null || true

        for _ in $(seq 1 60); do
            kill -0 "$pid" 2>/dev/null || break
            sleep 2
        done

        if kill -0 "$pid" 2>/dev/null; then
            echo "Worker did not stop after 120 seconds."
            echo "Sending SIGINT before considering anything stronger."

            kill -INT "$pid" 2>/dev/null || true

            for _ in $(seq 1 30); do
                kill -0 "$pid" 2>/dev/null || break
                sleep 2
            done
        fi
    fi

    unload_ollama

    # An AI worker can be interrupted while one record is marked running.
    # Once the worker is confirmed stopped, safely return that record to
    # pending so the next worker can retry it.
    sqlite3 "$DB" "
        UPDATE ai_jobs
        SET status = 'pending'
        WHERE status = 'running';
    "
}


cool_down() {

    local begin
    local now
    local elapsed
    local temp

    begin="$(date +%s)"

    echo
    echo "============================================================"
    echo " COOLDOWN"
    echo " Minimum cooldown : ${COOLDOWN_MIN_SECONDS}s"
    echo " Resume threshold : < ${START_TEMP}°C"
    echo "============================================================"

    while true; do

        sleep 30

        now="$(date +%s)"
        elapsed=$((now - begin))
        temp="$(get_temp)"

        echo "Cooldown: ${elapsed}s | Tctl=${temp:-unknown}°C"

        # Always provide at least a 10-minute break.
        if [ "$elapsed" -lt "$COOLDOWN_MIN_SECONDS" ]; then
            continue
        fi

        # After minimum cooldown, resume only once temperature is acceptable.
        if [ -n "$temp" ] && [ "$temp" -lt "$START_TEMP" ]; then
            echo "CPU cooled to ${temp}°C."
            return 0
        fi

        # Do not hang forever if sensor behavior is unusual.
        if [ "$elapsed" -ge "$MAX_COOLDOWN_SECONDS" ]; then
            echo "Maximum one-hour cooldown reached."
            echo "Continuing only if Tctl is below ${HARD_PAUSE_TEMP}°C."

            if [ -z "$temp" ] || [ "$temp" -ge "$HARD_PAUSE_TEMP" ]; then
                echo "Host is still too warm. Aborting today's AI run safely."
                exit 2
            fi

            return 0
        fi
    done
}


wait_until_initially_cool() {

    local temp

    while true; do

        temp="$(get_temp)"

        echo "Current Tctl: ${temp:-unknown}°C"

        if [ -n "$temp" ] && [ "$temp" -lt "$START_TEMP" ]; then
            return 0
        fi

        echo "Waiting for CPU to cool below ${START_TEMP}°C..."
        sleep 60
    done
}


t1000_running() {

    command -v virsh >/dev/null 2>&1 || return 1

    virsh list --state-running --name 2>/dev/null \
    | grep -Eiq '^T1000($|-|_)'
}


###############################################################################
# STOP OLD UNRESTRICTED WORKER
###############################################################################

echo
echo "============================================================"
echo " LOCAL EVENTS — FOUR CHUNK AI RUN"
echo " Started: $(date)"
echo "============================================================"
echo

OLD_PID="$(cat "$STATE/ai-final-regional.pid" 2>/dev/null || true)"

if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Existing first-run worker detected: PID $OLD_PID"
    stop_worker "$OLD_PID"
else
    echo "No active original AI worker detected."
fi

rm -f "$STATE/ai-final-regional.pid"


###############################################################################
# SAFETY CHECK
###############################################################################

if t1000_running; then
    echo
    echo "T1000 is running."
    echo "AI processing is not allowed concurrently with T1000."
    echo "Leaving the AI queue untouched."
    exit 3
fi


###############################################################################
# INITIAL QUEUE
###############################################################################

echo
echo "===== QUEUE AFTER OLD WORKER STOP ====="
queue_report

TOTAL="$(pending_jobs)"

if [ -z "$TOTAL" ] || [ "$TOTAL" -eq 0 ]; then
    echo
    echo "No pending AI jobs."
    echo "Nothing needs chunking."
    exit 0
fi

echo
echo "Pending jobs to process today: $TOTAL"


###############################################################################
# CALCULATE FOUR CHUNKS
#
# Example:
# 307 pending -> 77 / 77 / 77 / 76
###############################################################################

BASE=$((TOTAL / 4))
EXTRA=$((TOTAL % 4))

declare -a CHUNKS

for n in 1 2 3 4; do

    size="$BASE"

    if [ "$n" -le "$EXTRA" ]; then
        size=$((size + 1))
    fi

    CHUNKS[$n]="$size"
done

echo
echo "===== FOUR-CHUNK PLAN ====="

for n in 1 2 3 4; do
    echo "Chunk $n: ${CHUNKS[$n]} jobs"
done


###############################################################################
# COOL BEFORE FIRST CHUNK
###############################################################################

echo
echo "Cooling host before Chunk 1..."

unload_ollama

# First-run import is intentionally receiving a full cooldown before
# the first new chunk as well.
cool_down


###############################################################################
# PROCESS FOUR CHUNKS
###############################################################################

for CHUNK in 1 2 3 4; do

    QUOTA="${CHUNKS[$CHUNK]}"

    # Nothing assigned to this chunk.
    if [ "$QUOTA" -le 0 ]; then
        continue
    fi

    CHUNK_START_PENDING="$(pending_jobs)"

    if [ "$CHUNK_START_PENDING" -le 0 ]; then
        echo "Queue already completed."
        break
    fi

    # Never ask a chunk to process more jobs than remain.
    if [ "$QUOTA" -gt "$CHUNK_START_PENDING" ]; then
        QUOTA="$CHUNK_START_PENDING"
    fi

    TARGET_PENDING=$((CHUNK_START_PENDING - QUOTA))

    echo
    echo "============================================================"
    echo " CHUNK $CHUNK OF 4"
    echo " Starting pending : $CHUNK_START_PENDING"
    echo " Chunk quota      : $QUOTA"
    echo " Stop at pending  : <= $TARGET_PENDING"
    echo " Started          : $(date)"
    echo "============================================================"

    CHUNK_LOG="$LOGDIR/ai-chunk-${CHUNK}-$(date +%Y%m%d-%H%M%S).log"

    "$PY" \
        -m app.services.ai_batch \
        --execute \
        >>"$CHUNK_LOG" 2>&1 &

    PID=$!

    echo "$PID" > "$STATE/ai-four-chunk-current.pid"

    echo "Worker PID: $PID"
    echo "Log: $CHUNK_LOG"

    while kill -0 "$PID" 2>/dev/null; do

        sleep "$CHECK_SECONDS"

        NOW_PENDING="$(pending_jobs)"
        TEMP="$(get_temp)"

        DONE=$((CHUNK_START_PENDING - NOW_PENDING))

        echo \
            "$(date '+%F %T') | " \
            "chunk=$CHUNK | " \
            "done=$DONE/$QUOTA | " \
            "pending=$NOW_PENDING | " \
            "Tctl=${TEMP:-unknown}°C"

        #######################################################################
        # QUOTA COMPLETE
        #######################################################################

        if [ "$NOW_PENDING" -le "$TARGET_PENDING" ]; then

            echo
            echo "Chunk $CHUNK quota reached."

            stop_worker "$PID"

            break
        fi


        #######################################################################
        # THERMAL PAUSE INSIDE A CHUNK
        #
        # This does not count as a completed chunk.
        # We cool, then resume the SAME chunk.
        #######################################################################

        if [ -n "$TEMP" ] && [ "$TEMP" -ge "$HARD_PAUSE_TEMP" ]; then

            echo
            echo "THERMAL PAUSE: ${TEMP}°C >= ${HARD_PAUSE_TEMP}°C"

            stop_worker "$PID"

            cool_down

            # Recalculate amount remaining in this same conceptual chunk.
            CURRENT_PENDING="$(pending_jobs)"

            if [ "$CURRENT_PENDING" -le "$TARGET_PENDING" ]; then
                echo "Chunk quota completed while worker was stopping."
                break
            fi

            echo "Resuming Chunk $CHUNK after thermal cooldown..."

            "$PY" \
                -m app.services.ai_batch \
                --execute \
                >>"$CHUNK_LOG" 2>&1 &

            PID=$!

            echo "$PID" > "$STATE/ai-four-chunk-current.pid"

            echo "Replacement worker PID: $PID"
        fi

    done


    rm -f "$STATE/ai-four-chunk-current.pid"

    echo
    echo "===== QUEUE AFTER CHUNK $CHUNK ====="
    queue_report


    ###########################################################################
    # COOLDOWN BETWEEN CHUNKS
    ###########################################################################

    if [ "$CHUNK" -lt 4 ] && [ "$(pending_jobs)" -gt 0 ]; then
        unload_ollama
        cool_down
    fi

done


###############################################################################
# FINALIZE
###############################################################################

unload_ollama

echo
echo "============================================================"
echo " FOUR-CHUNK AI RUN FINISHED"
echo " Time: $(date)"
echo "============================================================"

echo
echo "===== FINAL AI QUEUE ====="
queue_report

PENDING="$(pending_jobs)"

if [ "$PENDING" -eq 0 ]; then

    echo
    echo "AI queue is clear."
    echo "Running final Local Events production pass..."

    "$PY" -m app.services.seasonal_priority
    "$PY" -m app.services.scoring
    "$PY" -m app.services.ha_publish

    echo
    echo "LOCAL EVENTS INITIAL AI PROCESSING: COMPLETE"

else

    echo
    echo "$PENDING pending AI jobs remain."
    echo "They are preserved in SQLite."
    echo "No data has been discarded."

fi

echo
echo "===== FINAL TEMPERATURE ====="
sensors 2>/dev/null | sed -n '/k10temp/,+4p'
