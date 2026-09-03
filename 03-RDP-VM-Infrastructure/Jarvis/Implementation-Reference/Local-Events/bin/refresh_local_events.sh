#!/usr/bin/env bash

set -u
set -o pipefail

ROOT="/mnt/appdata/ha-services/local-events"
PY="$ROOT/.venv/bin/python"
LOGDIR="$ROOT/logs"

cd "$ROOT" || exit 1

mkdir -p "$LOGDIR" state

exec 9>/run/lock/local-events-refresh.lock

if ! flock -n 9; then
    echo "Another Local Events refresh is already running."
    exit 0
fi

STAMP="$(date '+%Y%m%d-%H%M%S')"
LOG="$LOGDIR/refresh-$STAMP.log"

exec > >(tee -a "$LOG") 2>&1

echo "========================================================================"
echo " LOCAL EVENTS SCHEDULED REFRESH"
echo "========================================================================"
echo "Started: $(date)"
echo


run_step() {

    local name="$1"
    shift

    echo
    echo "========================================================================"
    echo " $name"
    echo "========================================================================"

    if "$@"; then
        echo "$name: PASS"
    else
        rc=$?
        echo "$name: WARNING / FAILED rc=$rc"
        return 0
    fi
}


###############################################################################
# FAST SOURCES
###############################################################################

run_step \
    "FAST OFFICIAL SOURCES" \
    "$PY" \
    -m app.collectors.official_web_events


###############################################################################
# ORIGINAL TRAVEL BROWSER FALLBACKS
#
# Ober
# Nashville / Visit Music City
# Visit Mobile
# Visit Orlando
###############################################################################

run_step \
    "TRAVEL BROWSER FALLBACKS" \
    "$PY" \
    -m app.collectors.browser_fallback_events


###############################################################################
# REGIONAL JAVASCRIPT / SPECIALTY SOURCES
###############################################################################

run_step \
    "REGIONAL BROWSER SOURCES" \
    "$PY" \
    -m app.collectors.regional_browser_runner \
    --source "We Are Huntsville" \
    --source "MidCity District" \
    --source "U.S. Space & Rocket Center" \
    --source "Ditto Landing" \
    --source "City of Mobile Events" \
    --source "Mobile Carnival Museum" \
    --source "Saenger Theatre Mobile" \
    --source "Daytona International Speedway" \
    --source "Peabody Auditorium / Oceanfront Bandshell" \
    --source "Official Daytona Bike Week" \
    --source "Pensacola Seafood Festival" \
    --source "Pensacola Mardi Gras" \
    --source "Pensacola Beach What's Happening" \
    --source "Bands on the Beach" \
    --source "Birmingham Zoo" \
    --source "Birmingham Botanical Gardens" \
    --source "Railroad Park" \
    --source "Alabama Symphony Orchestra" \
    --source "Saturn Birmingham" \
    --source "Avondale Brewing Company" \
    --source "Iron City Birmingham" \
    --source "Dollywood Festivals & Events"


###############################################################################
# NORMALIZE / GEOGRAPHY
###############################################################################

run_step \
    "DEDUPE" \
    "$PY" \
    -m app.services.deduplicate

run_step \
    "GEOCODING" \
    "$PY" \
    -m app.services.geocode_events

run_step \
    "DISTANCE TIERS" \
    "$PY" \
    -m app.services.distance


###############################################################################
# AI
#
# Never load the Local Events model while T1000 is running.
###############################################################################

T1000_STATE="$(
    virsh domstate T1000-Topology 2>/dev/null \
    | tr -d '\r' \
    | xargs \
    || true
)"

if [[ "$T1000_STATE" == "running" ]]; then

    echo
    echo "========================================================================"
    echo " AI"
    echo "========================================================================"

    echo "T1000-Topology is running."
    echo "AI classification skipped for this refresh."
    echo "Pending jobs will remain queued."

elif pgrep -af \
    "app.services.ai_batch.*--execute" \
    >/dev/null
then

    echo
    echo "========================================================================"
    echo " AI"
    echo "========================================================================"

    echo "Existing AI batch already running."
    echo "Not starting a second worker."

else

    run_step \
        "THERMALLY GOVERNED AI CLASSIFICATION" \
        "$ROOT/bin/run_ai_thermal.sh"

fi


###############################################################################
# PRIORITY / SCORING
###############################################################################

run_step \
    "SEASONAL PRIORITY" \
    "$PY" \
    -m app.services.seasonal_priority

run_step \
    "EVENT SCORING" \
    "$PY" \
    -m app.services.scoring


###############################################################################
# HOME ASSISTANT
###############################################################################

run_step \
    "HOME ASSISTANT PUBLISH" \
    "$PY" \
    -m app.services.ha_publish


###############################################################################
# FINAL STATUS
###############################################################################

echo
echo "========================================================================"
echo " FINAL DATABASE STATUS"
echo "========================================================================"

sqlite3 -header -column \
    data/local_events.db '
SELECT
    COUNT(*) AS active,
    SUM(tier = "T1") AS t1,
    SUM(tier = "T2") AS t2,
    SUM(tier = "T3") AS t3,
    SUM(ai_processed = 0) AS awaiting_ai
FROM events
WHERE canonical = 1
  AND active = 1;
'

echo

sqlite3 -header -column \
    data/local_events.db '
SELECT
    status,
    COUNT(*) AS jobs
FROM ai_jobs
GROUP BY status
ORDER BY status;
'

echo
echo "Dashboard health:"

curl -fsS \
    http://127.0.0.1:8787/health \
    || true

echo
echo
echo "Completed: $(date)"
echo "Log: $LOG"
echo "========================================================================"
