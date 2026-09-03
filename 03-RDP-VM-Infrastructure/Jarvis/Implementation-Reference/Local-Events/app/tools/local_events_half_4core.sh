#!/usr/bin/env bash

ROOT="/mnt/appdata/ha-services/local-events"
DB="$ROOT/data/local_events.db"

SLICE_SECONDS=1200

PAUSE_TEMP=90
PREEMPT_TEMP=82
RESUME_TEMP=75
EMERGENCY_TEMP=92
BETWEEN_SLICE_TEMP=75

BATCH_PID=""
RUNNER_PAUSED=0
PAUSED_PIDS=""

cd "$ROOT" || exit 1


read_temp() {

    local highest=""
    local name=""
    local label=""
    local raw=""

    for HWMON in /sys/class/hwmon/hwmon*; do

        name="$(
            cat "$HWMON/name" 2>/dev/null
        )"

        [[ "$name" == "k10temp" ]] || continue

        for INPUT in "$HWMON"/temp*_input; do

            [[ -f "$INPUT" ]] || continue

            label="$(
                cat "${INPUT%_input}_label" \
                    2>/dev/null
            )"

            if [[ "$label" != "Tctl" \
               && "$label" != "Tdie" ]]
            then
                continue
            fi

            raw="$(
                cat "$INPUT" 2>/dev/null
            )"

            [[ "$raw" =~ ^[0-9]+$ ]] || continue

            if [[ -z "$highest" \
               || "$raw" -gt "$highest" ]]
            then
                highest="$raw"
            fi
        done
    done

    [[ "$highest" =~ ^[0-9]+$ ]] || return 1

    awk -v raw="$highest" \
        'BEGIN {
            printf "%.1f", raw / 1000
        }'
}


temp_ge() {

    awk \
        -v temp="$1" \
        -v limit="$2" \
        'BEGIN {
            exit !(temp >= limit)
        }'
}


temp_le() {

    awk \
        -v temp="$1" \
        -v limit="$2" \
        'BEGIN {
            exit !(temp <= limit)
        }'
}


completed_count() {

    sqlite3 "$DB" "
    SELECT COUNT(*)
    FROM ai_jobs
    WHERE status = 'completed';
    "
}


eligible_pending() {

    sqlite3 "$DB" "
    SELECT COUNT(*)
    FROM ai_jobs j
    JOIN events e
      ON e.id = j.event_id
    WHERE j.status = 'pending'
      AND j.job_type = 'classify_event'
      AND e.canonical = 1
      AND e.active = 1;
    "
}


media_active() {

    pgrep -af \
        '([H]andBrakeCLI|[f]fmpeg|[d]vdbackup|[m]akemkvcon|[d]drescue|[c]dparanoia|jarvis_local_dvd_worker|jarvis_movie_.*ingest|jarvis_disc_.*ingest)' \
        2>/dev/null
}


knowledge_active() {

    pgrep -af \
        '(jarvis-index|jarvis-search|jarvis-sync)' \
        2>/dev/null
}


pause_phi3() {

    PAUSED_PIDS="$(
        pgrep -f \
            '^/usr/local/bin/ollama runner ' \
            2>/dev/null || true
    )"

    if [[ -n "$PAUSED_PIDS" ]]; then

        kill -STOP $PAUSED_PIDS \
            2>/dev/null || true

        RUNNER_PAUSED=1

        echo "⏸ Phi-3 runner paused"

    else

        echo "⚠️ No Ollama runner PID found to pause"

    fi
}


resume_phi3() {

    if (( RUNNER_PAUSED == 1 )); then

        if [[ -n "$PAUSED_PIDS" ]]; then

            kill -CONT $PAUSED_PIDS \
                2>/dev/null || true

        fi

        RUNNER_PAUSED=0
        PAUSED_PIDS=""

        echo "▶ Phi-3 runner resumed"
    fi
}


recover_running_jobs() {

    if pgrep -f \
        'app[.]services[.]ai_batch.*--execute' \
        >/dev/null 2>&1
    then
        return
    fi

    sqlite3 "$DB" "
    UPDATE ai_jobs
    SET
        status = 'pending',
        started_at = NULL,
        error =
            'Recovered after Local Events 4-core duty-cycle boundary.'
    WHERE status = 'running'
      AND job_type = 'classify_event';
    "
}


stop_current_batch() {

    resume_phi3

    if [[ -n "$BATCH_PID" ]] \
       && kill -0 "$BATCH_PID" 2>/dev/null
    then

        kill -INT "$BATCH_PID" \
            2>/dev/null || true

        sleep 2
    fi

    ollama stop gemma3:1b \
        >/dev/null 2>&1 || true

    sleep 1

    recover_running_jobs
}


cleanup() {

    echo
    echo "===== DUTY-CYCLE CLEANUP ====="

    stop_current_batch
}


trap cleanup INT TERM


echo "============================================================"
echo " LOCAL EVENTS — 4-CORE HALF-BACKLOG CAMPAIGN"
echo "============================================================"

echo "Slice:           20 minutes"
echo "Ollama ceiling:  4 cores / 400%"
echo "Pause:           ${PAUSE_TEMP}C"
echo "Resume:          ${RESUME_TEMP}C"
echo "Emergency:       ${EMERGENCY_TEMP}C"
echo


#
# ----------------------------------------------------------
# VERIFY 4-CORE POLICY
# ----------------------------------------------------------
#

echo "===== OLLAMA CPU POLICY ====="

CURRENT_QUOTA="$(
    systemctl show ollama.service \
        -p CPUQuotaPerSecUSec \
        --value
)"

if [[ "$CURRENT_QUOTA" != "4s" ]]; then

    echo "Restoring normal 4-core ceiling..."

    if command -v ollama-ceiling \
        >/dev/null 2>&1
    then

        ollama-ceiling daily

    else

        sudo systemctl set-property \
            --runtime \
            ollama.service \
            CPUQuota=400%
    fi
fi

systemctl show ollama.service \
    -p CPUQuotaPerSecUSec \
    -p ActiveState


#
# ----------------------------------------------------------
# PRE-FLIGHT
# ----------------------------------------------------------
#

echo
echo "===== PRE-FLIGHT ====="

TEMP="$(read_temp || true)"

if [[ -z "$TEMP" ]]; then
    echo "❌ BLOCK: Tctl/Tdie unavailable."
    exit 2
fi

echo "Tctl: ${TEMP}C"

if media_active >/dev/null; then

    echo "❌ BLOCK: media workload active."
    media_active
    exit 2

fi

if knowledge_active >/dev/null; then

    echo "❌ BLOCK: knowledge workload active."
    knowledge_active
    exit 2

fi

if pgrep -f \
    'app[.]services[.]ai_batch.*--execute' \
    >/dev/null 2>&1
then

    echo "❌ BLOCK: another Local Events AI batch exists."
    exit 2
fi

echo "✅ Media idle"
echo "✅ Knowledge pipeline idle"
echo "✅ Local Events AI idle"


#
# ----------------------------------------------------------
# DATABASE SAFETY SNAPSHOT
# ----------------------------------------------------------
#

STAMP="$(date +%Y%m%d-%H%M%S)"

sqlite3 "$DB" \
    ".backup 'backups/local_events-pre-half-campaign-$STAMP.db'"

echo "✅ Database backup complete"


#
# ----------------------------------------------------------
# FIXED CAMPAIGN TARGET
# ----------------------------------------------------------
#

START_PENDING="$(eligible_pending)"
START_COMPLETED="$(completed_count)"

# Original campaign:
# 201 completed + 620 requested = 821 final completed jobs.
FINAL_COMPLETED_TARGET=821

if (( START_COMPLETED >= FINAL_COMPLETED_TARGET )); then
    TARGET=0
else
    TARGET=$((FINAL_COMPLETED_TARGET - START_COMPLETED))
fi

TARGET_COMPLETED="$FINAL_COMPLETED_TARGET"

echo
echo "===== CAMPAIGN TARGET ====="

echo "Eligible pending:     $START_PENDING"
echo "Already completed:    $START_COMPLETED"
echo "Campaign target:      $TARGET"
echo "Stop at completed:    $TARGET_COMPLETED"

if (( TARGET <= 0 )); then
    echo "Nothing to process."
    exit 0
fi


SLICE=0
NO_PROGRESS=0


#
# ==========================================================
# CAMPAIGN LOOP
# ==========================================================
#

while true; do

    CURRENT_COMPLETED="$(completed_count)"
    DONE=$((CURRENT_COMPLETED - START_COMPLETED))

    if (( DONE >= TARGET )); then

        echo
        echo "✅ HALF-BACKLOG TARGET REACHED"
        break

    fi

    REMAINING=$((TARGET - DONE))

    SLICE=$((SLICE + 1))

    echo
    echo "============================================================"
    echo " SLICE $SLICE"
    echo " COMPLETED $DONE / $TARGET"
    echo "============================================================"


    #
    # Wait if a higher-priority workload exists.
    #

    while media_active >/dev/null \
       || knowledge_active >/dev/null
    do

        echo
        echo "⏸ Jarvis resource lane occupied."

        media_active || true
        knowledge_active || true

        echo "Checking again in 30 seconds..."

        sleep 30
    done


    #
    # Cool to 75C before each slice.
    #

    echo
    echo "===== PRE-SLICE THERMAL GATE ====="

    while true; do

        TEMP="$(read_temp || true)"

        if [[ -z "$TEMP" ]]; then
            echo "❌ Thermal sensor unavailable."
            exit 3
        fi

        echo "$(date '+%H:%M:%S') — ${TEMP}C"

        if temp_le \
            "$TEMP" \
            "$BETWEEN_SLICE_TEMP"
        then

            echo "✅ CPU ready"
            break

        fi

        sleep 3
    done


    #
    # Give Phi-3 exclusive Ollama ownership.
    #

    ollama stop embeddinggemma:latest \
        >/dev/null 2>&1 || true

    ollama stop gemma3:1b \
        >/dev/null 2>&1 || true

    sleep 2


    BEFORE_SLICE="$(completed_count)"

    echo
    echo "===== START SLICE $SLICE ====="
    echo "Remaining target: $REMAINING"


    .venv/bin/python \
        -m app.services.ai_batch \
        --execute \
        --limit "$REMAINING" \
        --keep-alive 10m &

    BATCH_PID=$!

    SLICE_START=$SECONDS
    LAST_REPORT=0
    EMERGENCY=0
    STOP_REASON=""


    #
    # ------------------------------------------------------
    # ONE-SECOND THERMAL SUPERVISION
    # ------------------------------------------------------
    #

    while kill -0 "$BATCH_PID" 2>/dev/null; do

        TEMP="$(read_temp || true)"
        ELAPSED=$((SECONDS - SLICE_START))

        if [[ -z "$TEMP" ]]; then

            echo
            echo "❌ Thermal sensor failure."

            STOP_REASON="sensor-failure"
            EMERGENCY=1
            break
        fi


        #
        # Absolute emergency ceiling.
        #

        if temp_ge \
            "$TEMP" \
            "$EMERGENCY_TEMP"
        then

            echo
            echo "🔥 $(date '+%H:%M:%S') — ${TEMP}C"
            echo "EMERGENCY STOP AT ${EMERGENCY_TEMP}C"

            STOP_REASON="thermal-emergency"
            EMERGENCY=1

            #
            # If the runner was thermally frozen, wake it only
            # so it can be terminated. Do NOT resume inference.
            #
            if (( RUNNER_PAUSED == 1 )); then

                if [[ -n "$PAUSED_PIDS" ]]; then
                    kill -CONT $PAUSED_PIDS                         2>/dev/null || true
                fi

                RUNNER_PAUSED=0
                PAUSED_PIDS=""
            fi

            #
            # Terminate the classification process immediately.
            #
            if kill -0 "$BATCH_PID" 2>/dev/null; then
                kill -TERM "$BATCH_PID"                     2>/dev/null || true
            fi

            #
            # Unload Phi-3 immediately.
            #
            ollama stop gemma3:1b                 >/dev/null 2>&1 || true

            sleep 2

            #
            # Escalate if Python ignored TERM.
            #
            if kill -0 "$BATCH_PID" 2>/dev/null; then
                echo "⚠️ Batch resisted TERM — forcing shutdown."

                kill -KILL "$BATCH_PID"                     2>/dev/null || true
            fi

            break
        fi


        #
        # Pause at 90C.
        #

        if (( RUNNER_PAUSED == 0 )) \
           && temp_ge \
                "$TEMP" \
                "$PREEMPT_TEMP"
        then

            echo
            echo "🌡 $(date '+%H:%M:%S') — ${TEMP}C"
            echo "PREEMPTIVE THERMAL BRAKE"
            echo "Freezing Phi-3 before the ${PAUSE_TEMP}C ceiling."

            pause_phi3
        fi


        #
        # Resume at 75C.
        #

        if (( RUNNER_PAUSED == 1 )) \
           && temp_le \
                "$TEMP" \
                "$RESUME_TEMP"
        then

            echo
            echo "❄️ $(date '+%H:%M:%S') — ${TEMP}C"
            echo "RESUME THRESHOLD REACHED"

            resume_phi3
        fi


        #
        # Progress display every 10 seconds.
        #

        if (( ELAPSED - LAST_REPORT >= 10 )); then

            CURRENT_COMPLETED="$(completed_count)"
            DONE=$((CURRENT_COMPLETED - START_COMPLETED))

            STATE="RUNNING"

            if (( RUNNER_PAUSED == 1 )); then
                STATE="THERMAL-PAUSED"
            fi

            echo \
                "$(date '+%H:%M:%S') | ${TEMP}C | $STATE | ${DONE}/${TARGET} complete"

            LAST_REPORT=$ELAPSED
        fi


        #
        # 20-minute slice boundary.
        #

        if (( ELAPSED >= SLICE_SECONDS )); then

            echo
            echo "⏱ 20-MINUTE SLICE COMPLETE"

            STOP_REASON="20-minute-boundary"
            break
        fi


        #
        # Higher-priority work gets the machine.
        #

        if (( ELAPSED % 5 == 0 )); then

            if media_active >/dev/null; then

                echo
                echo "⏸ Media workload appeared."

                STOP_REASON="media-priority"
                break
            fi

            if knowledge_active >/dev/null; then

                echo
                echo "⏸ Knowledge workload appeared."

                STOP_REASON="knowledge-priority"
                break
            fi
        fi

        sleep 1
    done


    #
    # ------------------------------------------------------
    # END CURRENT SLICE
    # ------------------------------------------------------
    #

    resume_phi3

    if kill -0 "$BATCH_PID" 2>/dev/null; then

        kill -INT "$BATCH_PID" \
            2>/dev/null || true

    fi

    wait "$BATCH_PID"
    RC=$?

    BATCH_PID=""

    ollama stop gemma3:1b \
        >/dev/null 2>&1 || true

    sleep 2

    recover_running_jobs


    AFTER_SLICE="$(completed_count)"
    SLICE_DONE=$((AFTER_SLICE - BEFORE_SLICE))
    TOTAL_DONE=$((AFTER_SLICE - START_COMPLETED))

    echo
    echo "===== SLICE $SLICE RESULT ====="

    echo "Stop reason:        ${STOP_REASON:-batch-finished}"
    echo "Exit code:          $RC"
    echo "Completed slice:    $SLICE_DONE"
    echo "Campaign progress:  $TOTAL_DONE / $TARGET"

    TEMP="$(read_temp || true)"
    echo "Current Tctl:       ${TEMP:-UNKNOWN}C"


    #
    # Avoid an infinite heat/retry loop.
    #

    if (( SLICE_DONE == 0 )); then
        NO_PROGRESS=$((NO_PROGRESS + 1))
    else
        NO_PROGRESS=0
    fi

    if (( NO_PROGRESS >= 3 )); then

        echo
        echo "🛑 Three consecutive slices produced no completed jobs."
        echo "Stopping campaign for inspection."
        break
    fi


    if (( EMERGENCY == 1 )); then

        echo
        echo "Cooling after emergency stop..."

        while true; do

            TEMP="$(read_temp || true)"

            [[ -n "$TEMP" ]] || break

            echo "$(date '+%H:%M:%S') — ${TEMP}C"

            if temp_le \
                "$TEMP" \
                "$RESUME_TEMP"
            then
                break
            fi

            sleep 3
        done
    fi

done


#
# ==========================================================
# FINAL RESULTS
# ==========================================================
#

FINAL_COMPLETED="$(completed_count)"
TOTAL_DONE=$((FINAL_COMPLETED - START_COMPLETED))

echo
echo "============================================================"
echo " CAMPAIGN RESULT"
echo "============================================================"

echo "Requested classifications: $TARGET"
echo "Completed classifications: $TOTAL_DONE"

echo
echo "===== QUEUE ====="

sqlite3 -header -column "$DB" "
SELECT
    status,
    COUNT(*) AS jobs
FROM ai_jobs
GROUP BY status
ORDER BY status;
"


if (( TOTAL_DONE >= TARGET )); then

    echo
    echo "===== DETERMINISTIC FACT REPAIR ====="

    .venv/bin/python \
        -m app.services.repair_ai_facts

    echo
    echo "===== SEASONAL PRIORITY ====="

    .venv/bin/python \
        -m app.services.seasonal_priority

    echo
    echo "===== SCORING ====="

    .venv/bin/python \
        -m app.services.scoring

else

    echo
    echo "⚠️ Target not yet reached."
    echo "All successful classifications remain committed."
    echo "Remaining jobs remain pending."

fi


echo
echo "===== FINAL COVERAGE ====="

sqlite3 -header -column "$DB" "
SELECT
    COUNT(*) AS active_canonical,

    SUM(
        CASE
            WHEN ai_processed = 1
            THEN 1
            ELSE 0
        END
    ) AS ai_processed,

    SUM(
        CASE
            WHEN ai_processed = 0
            THEN 1
            ELSE 0
        END
    ) AS awaiting_ai

FROM events

WHERE active = 1
  AND canonical = 1;
"


echo
echo "===== FINAL THERMALS ====="

TEMP="$(read_temp || true)"

echo "Tctl: ${TEMP:-UNKNOWN}C"


echo
echo "===== OLLAMA POLICY ====="

systemctl show ollama.service \
    -p CPUQuotaPerSecUSec \
    -p ActiveState

ollama ps


echo
echo "============================================================"
echo " LOCAL EVENTS DUTY-CYCLE CAMPAIGN FINISHED"
echo "============================================================"
