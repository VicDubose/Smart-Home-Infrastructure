#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="/mnt/appdata/ha-services/local-events"
DB="$ROOT/data/local_events.db"
PY="$ROOT/.venv/bin/python"
MODEL="gemma3:1b"

START_MAX=60
STOP_TEMP=90
SAMPLE_SECONDS=1
WAIT_SECONDS=15

WORKER_PID=""

cd "$ROOT"

exec 9>"$ROOT/state/gemma-backlog.lock"
flock -n 9 || {
    echo "ERROR: Gemma backlog processor already running."
    exit 10
}

temp() {
    sensors 2>/dev/null |
    awk '/Tctl:/ {
        gsub(/[+°C]/,"",$2)
        print $2
        exit
    }'
}

ge() {
    awk -v a="$1" -v b="$2" 'BEGIN {exit !(a >= b)}'
}

le() {
    awk -v a="$1" -v b="$2" 'BEGIN {exit !(a <= b)}'
}

count_status() {
    sqlite3 "$DB" \
        "SELECT COUNT(*) FROM ai_jobs WHERE status='$1';"
}

media_active() {
    pgrep -f \
      'dvdbackup|makemkvcon|makemkv|HandBrakeCLI|ffmpeg|jarvis.*burn' \
      >/dev/null 2>&1
}

t1000_active() {
    pgrep -afi 'T1000-Topology|t1000' >/dev/null 2>&1
}

recover_running() {
    sqlite3 "$DB" '
    UPDATE ai_jobs
    SET
        status="pending",
        started_at=NULL
    WHERE status="running";
    '
}

stop_worker() {
    if [ -n "${WORKER_PID:-}" ] &&
       kill -0 "$WORKER_PID" 2>/dev/null; then

        kill -TERM "$WORKER_PID" 2>/dev/null || true

        for _ in $(seq 1 10); do
            kill -0 "$WORKER_PID" 2>/dev/null || break
            sleep 1
        done

        if kill -0 "$WORKER_PID" 2>/dev/null; then
            kill -KILL "$WORKER_PID" 2>/dev/null || true
        fi

        wait "$WORKER_PID" 2>/dev/null || true
    fi

    WORKER_PID=""
    recover_running
    ollama stop "$MODEL" >/dev/null 2>&1 || true
}

cleanup() {
    trap - EXIT
    stop_worker || true
}

trap cleanup EXIT
trap 'exit 143' TERM INT

echo "============================================================"
echo " LOCAL EVENTS — GEMMA BACKLOG PROCESSOR"
echo "============================================================"

echo
echo "Model:         $MODEL"
echo "Ollama CPUs:   4-7"
echo "CPU quota:     250%"
echo "Start temp:    <= ${START_MAX}C"
echo "Stop temp:     >= ${STOP_TEMP}C"
echo "Thermal poll:  ${SAMPLE_SECONDS}s"

echo
echo "===== PREFLIGHT ====="

grep -Eq \
  '^[[:space:]]*model:[[:space:]]*gemma3:1b' \
  config/local-events.yaml || {
    echo "ERROR: gemma3:1b is not configured."
    exit 11
}

ollama list |
awk 'NR>1 {print $1}' |
grep -Fxq "$MODEL" || {
    echo "ERROR: $MODEL is not installed."
    exit 12
}

[ "$(sqlite3 "$DB" 'PRAGMA integrity_check;')" = "ok" ] || {
    echo "ERROR: database integrity failed."
    exit 13
}

recover_running

echo
echo "===== STARTING QUEUE ====="

sqlite3 -header -column "$DB" '
SELECT status, COUNT(*) AS jobs
FROM ai_jobs
GROUP BY status
ORDER BY status;
'

echo
echo "===== PROCESS BACKLOG ====="

while true; do

    PENDING="$(count_status pending)"

    if [ "$PENDING" -eq 0 ]; then
        break
    fi

    echo
    echo "------------------------------------------------------------"
    echo "Pending jobs: $PENDING"
    echo "------------------------------------------------------------"

    #
    # Wait for other heavy workloads.
    #
    while media_active || t1000_active; do
        echo "$(date '+%F %T') — competing workload active; Gemma waiting."
        sleep "$WAIT_SECONDS"
    done

    #
    # Wait until CPU has cooled enough for another AI wave.
    #
    while true; do

        T="$(temp || true)"

        if [ -z "$T" ]; then
            echo "$(date '+%F %T') — Tctl unavailable; waiting."
            sleep "$WAIT_SECONDS"
            continue
        fi

        echo "$(date '+%F %T') — cooling gate: ${T}C"

        if le "$T" "$START_MAX"; then
            break
        fi

        sleep "$WAIT_SECONDS"
    done

    BEFORE="$(count_status completed)"

    echo
    echo "Launching $MODEL"
    echo "Completed before: $BEFORE"
    echo "Pending before:   $PENDING"

    taskset -c 4-7 \
      "$PY" -m app.services.ai_batch --execute &

    WORKER_PID=$!

    SECONDS_RUNNING=0
    STOP_REASON="natural"

    while kill -0 "$WORKER_PID" 2>/dev/null; do

        sleep "$SAMPLE_SECONDS"
        SECONDS_RUNNING=$((SECONDS_RUNNING + 1))

        T="$(temp || true)"

        if media_active; then
            echo
            echo "MEDIA WORK DETECTED — yielding AI."
            STOP_REASON="media"
            stop_worker
            break
        fi

        if t1000_active; then
            echo
            echo "T1000 DETECTED — yielding AI."
            STOP_REASON="t1000"
            stop_worker
            break
        fi

        if [ -n "$T" ] && ge "$T" "$STOP_TEMP"; then
            echo
            echo "THERMAL STOP: ${T}C >= ${STOP_TEMP}C"
            STOP_REASON="thermal"
            stop_worker
            break
        fi

        if [ $((SECONDS_RUNNING % 15)) -eq 0 ]; then
            printf '%s | %ss | Tctl=%sC | completed=%s | pending=%s | running=%s\n' \
              "$(date '+%F %T')" \
              "$SECONDS_RUNNING" \
              "${T:-?}" \
              "$(count_status completed)" \
              "$(count_status pending)" \
              "$(count_status running)"
        fi
    done

    if [ -n "${WORKER_PID:-}" ]; then
        wait "$WORKER_PID" 2>/dev/null || true
        WORKER_PID=""
    fi

    recover_running
    ollama stop "$MODEL" >/dev/null 2>&1 || true

    AFTER="$(count_status completed)"
    LEFT="$(count_status pending)"
    FINISHED=$((AFTER - BEFORE))

    echo
    echo "===== WAVE RESULT ====="
    echo "Reason:          $STOP_REASON"
    echo "Jobs completed:  $FINISHED"
    echo "Completed total: $AFTER"
    echo "Pending:         $LEFT"
    echo "Tctl:            $(temp || true)C"

    if [ "$LEFT" -eq 0 ]; then
        break
    fi

    #
    # Protection against an endless heat/cool loop where not even one
    # event can finish.
    #
    if [ "$STOP_REASON" = "thermal" ] &&
       [ "$FINISHED" -eq 0 ]; then

        echo
        echo "WARNING: thermal wave completed zero jobs."
        echo "Cooling fully and retrying once at the same safe policy."

        while true; do
            T="$(temp || true)"
            [ -n "$T" ] && le "$T" "$START_MAX" && break
            sleep "$WAIT_SECONDS"
        done
    fi

done

ollama stop "$MODEL" >/dev/null 2>&1 || true

echo
echo "============================================================"
echo " BACKLOG COMPLETE"
echo "============================================================"

sqlite3 -header -column "$DB" '
SELECT status, COUNT(*) AS jobs
FROM ai_jobs
GROUP BY status
ORDER BY status;
'

echo
echo "===== FINAL INTEGRITY ====="
sqlite3 "$DB" 'PRAGMA integrity_check;'

echo
echo "===== SEASONAL PRIORITY ====="
"$PY" -m app.services.seasonal_priority || true

echo
echo "===== EVENT SCORING ====="
"$PY" -m app.services.event_scoring || true

echo
echo "===== FINAL TEMP ====="
sensors | sed -n '/k10temp/,+4p'

echo
echo "✅ GEMMA BACKLOG PROCESSING FINISHED"
