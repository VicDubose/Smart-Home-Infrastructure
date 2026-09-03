#!/usr/bin/env bash

set -u

ROOT="/mnt/appdata/ha-services/local-events"
PY="$ROOT/.venv/bin/python"

START_LIMIT="80"
STOP_LIMIT="93"

cd "$ROOT" || exit 1


get_temp() {
    sensors 2>/dev/null \
    | awk '
        /^Tctl:/ {
            gsub(/[+°C]/, "", $2)
            print $2
            exit
        }
    '
}


TEMP="$(get_temp)"

echo "AI thermal governor"
echo "Current Tctl: ${TEMP:-unknown}°C"


if [ -n "$TEMP" ] && \
   awk "BEGIN {exit !($TEMP >= $START_LIMIT)}"
then
    echo "CPU is ${TEMP}°C."
    echo "AI skipped because start limit is ${START_LIMIT}°C."
    exit 0
fi


echo "Starting incremental AI batch."

"$PY" \
  -m app.services.ai_batch \
  --execute &

PID=$!

echo "AI PID: $PID"


while kill -0 "$PID" 2>/dev/null; do

    sleep 30

    TEMP="$(get_temp)"

    [ -n "$TEMP" ] || continue

    echo "AI Tctl: ${TEMP}°C"

    if awk "BEGIN {exit !($TEMP >= $STOP_LIMIT)}"
    then
        echo
        echo "THERMAL LIMIT REACHED: ${TEMP}°C"
        echo "Gracefully stopping AI batch."

        kill -TERM "$PID" 2>/dev/null || true

        wait "$PID" 2>/dev/null || true

        echo "Remaining jobs stay queued."
        exit 0
    fi
done


wait "$PID"
RC=$?

echo "AI batch exited rc=$RC"

exit "$RC"
