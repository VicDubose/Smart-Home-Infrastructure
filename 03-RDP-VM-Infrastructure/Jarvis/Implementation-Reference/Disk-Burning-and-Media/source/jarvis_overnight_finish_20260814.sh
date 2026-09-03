#!/usr/bin/env bash

set -u
set -o pipefail

STAMP="$(date +%Y%m%d-%H%M%S)"

LOGROOT="$HOME/Jarvis/logs/overnight-media"
WORK="$HOME/Jarvis/jobs/overnight-media-$STAMP"

mkdir -p "$LOGROOT" "$WORK"

LOG="$LOGROOT/overnight-$STAMP.log"

echo "$LOG" > "$HOME/Jarvis/jobs/overnight-media-current-log.txt"

exec > >(tee -a "$LOG") 2>&1

echo "================================================================"
echo " JARVIS OVERNIGHT MEDIA FINISH"
echo " Started: $(date)"
echo "================================================================"

TIMER="jarvis-media-priority.timer"
SERVICE="jarvis-media-priority.service"

TIMER_WAS_ACTIVE="$(systemctl --user is-active "$TIMER" 2>/dev/null || true)"
TIMER_RESTORED=0

restore_timer() {
    if [[ "$TIMER_RESTORED" -eq 0 && "$TIMER_WAS_ACTIVE" == "active" ]]; then
        echo
        echo "Restoring Jarvis media-priority timer."
        systemctl --user start "$TIMER" 2>/dev/null || true
    fi
}

trap restore_timer EXIT

echo
echo "===== TEMPORARILY PAUSE PRIORITY TIMER ====="

systemctl --user stop "$TIMER" 2>/dev/null || true

echo
echo "===== WAIT FOR CLEAN MEDIA SLOT ====="

while pgrep -f \
'[H]andBrakeCLI|[d]vdbackup|[j]arvis_disc_ingest_guarded|[j]arvis_validate|[j]arvis_move_if_valid' \
>/dev/null
do
    echo "$(date): media slot busy — waiting 60 seconds"
    sleep 60
done

echo "Media slot is clear."

###############################################################################
# HOGAN'S HEROES S3 DISC 4
###############################################################################

echo
echo "================================================================"
echo " HOGAN'S HEROES S3D4 — E19-E24"
echo "================================================================"

HOGAN_ROOT="/mnt/appdata/caleb-media/incoming/DVD/Hogans_Heroes_S3_D4_20260717_152026"
HOGAN_DEST="/mnt/media/Shows/Hogan's Heroes/Season 03"
HOGAN_PIPE="$HOME/rdp-scripts/Jarvis/media/jarvis_disc_ingest_guarded_v2.py"
HOGAN_STAGE="$HOME/Jarvis/jobs/hogans/S03D04-$STAMP"

HOGAN_VTS="$(
    find "$HOGAN_ROOT" \
      -type d \
      -name VIDEO_TS \
      ! -path '*.receiving*' \
      -print -quit 2>/dev/null
)"

HOGAN_MISSING=0

for ep in 19 20 21 22 23 24; do
    F="$HOGAN_DEST/Hogan's Heroes - S03E${ep}.mkv"

    if [[ -s "$F" ]]; then
        echo "S03E${ep} already exists."
    else
        echo "S03E${ep} missing."
        HOGAN_MISSING=$((HOGAN_MISSING + 1))
    fi
done

HOGAN_RAN=0
HOGAN_RC=0

if [[ "$HOGAN_MISSING" -eq 6 && -n "$HOGAN_VTS" ]]; then

    mkdir -p "$HOGAN_STAGE"

    echo
    echo "Source: $HOGAN_VTS"
    echo "Mapping: S03E19-S03E24"
    echo

    HOGAN_RAN=1

    env JARVIS_AUTO_CONFIRM=YES \
        nice -n 10 \
        ionice -c2 -n7 \
        python3 -u "$HOGAN_PIPE" \
          --show "Hogan's Heroes" \
          --season 3 \
          --disc 4 \
          --start 19 \
          --count 6 \
          --device "$HOGAN_VTS" \
          --staging "$HOGAN_STAGE" \
          --ai phi3:mini

    HOGAN_RC=$?

    echo
    echo "Hogan S3D4 return code: $HOGAN_RC"

elif [[ "$HOGAN_MISSING" -eq 0 ]]; then

    echo "Hogan S3D4 is already complete. Skipping."

else

    echo
    echo "SAFETY BLOCK:"
    echo "Hogan S3D4 is in a partial/ambiguous state."
    echo "It will NOT be automatically processed."
    echo "Movies will continue independently."

fi

if [[ "$HOGAN_RAN" -eq 1 && "$HOGAN_RC" -eq 0 ]]; then

    echo
    echo "===== 20-MINUTE POST-HOGAN REST ====="
    echo "Cooling/resting before movie work."
    sleep 1200

fi

###############################################################################
# COMBO MOVIE DVD
###############################################################################

echo
echo "================================================================"
echo " RAW MOVIE DVD — 7000080254_1"
echo "================================================================"

RAW="$(
    cat "$HOME/Jarvis/jobs/local-dvd-raw-current-job.txt" \
      2>/dev/null
)"

RAW_VTS=""

if [[ -n "$RAW" && -d "$RAW" ]]; then

    RAW_VTS="$(
        find "$RAW" \
          -type d \
          -name VIDEO_TS \
          -print -quit 2>/dev/null
    )"

fi

MOVIE_SAFE=0

if [[ -n "$RAW_VTS" ]]; then

    echo "Raw source: $RAW"
    echo "VIDEO_TS:   $RAW_VTS"

    SCAN="$WORK/movie-title-scan.txt"
    MAP="$WORK/movie-title-map.sh"

    echo
    echo "===== SCANNING RAW DVD ====="

    nice -n 10 \
        ionice -c2 -n7 \
        HandBrakeCLI \
          -i "$RAW_VTS" \
          -t 0 \
          --scan \
          >"$SCAN" 2>&1

    python3 - "$SCAN" "$MAP" <<'PY'
import re
import sys
from pathlib import Path

scan = Path(sys.argv[1])
mapping = Path(sys.argv[2])

text = scan.read_text(
    encoding="utf-8",
    errors="replace",
)

titles = []
current = None

for line in text.splitlines():

    m = re.match(r"\s*\+\s*title\s+(\d+):", line)

    if m:
        current = int(m.group(1))
        continue

    if current is None:
        continue

    m = re.match(
        r"\s*\+\s*duration:\s*(\d+):(\d+):(\d+)",
        line,
    )

    if not m:
        continue

    h, minute, sec = map(int, m.groups())

    seconds = (
        h * 3600
        + minute * 60
        + sec
    )

    titles.append(
        {
            "title": current,
            "seconds": seconds,
        }
    )

    current = None

features = sorted(
    [
        item
        for item in titles
        if 80 * 60 <= item["seconds"] <= 105 * 60
    ],
    key=lambda item: (
        item["seconds"],
        item["title"],
    ),
)

print("Feature-length candidates:")

for item in features:
    seconds = item["seconds"]

    print(
        f"  Title {item['title']:02d} "
        f"{seconds // 60}m {seconds % 60:02d}s"
    )

clusters = []

for item in features:

    placed = False

    for cluster in clusters:

        center = sum(
            x["seconds"]
            for x in cluster
        ) / len(cluster)

        if abs(item["seconds"] - center) <= 90:
            cluster.append(item)
            placed = True
            break

    if not placed:
        clusters.append([item])

clusters.sort(
    key=lambda cluster:
        sum(x["seconds"] for x in cluster)
        / len(cluster)
)

safe = False
rh3 = None
money = None

if len(clusters) == 2:

    short_center = sum(
        x["seconds"]
        for x in clusters[0]
    ) / len(clusters[0])

    long_center = sum(
        x["seconds"]
        for x in clusters[1]
    ) / len(clusters[1])

    separation = long_center - short_center

    if separation >= 180:

        rh3 = min(
            clusters[0],
            key=lambda x: x["title"],
        )

        money = min(
            clusters[1],
            key=lambda x: x["title"],
        )

        safe = True

with mapping.open("w") as f:

    if safe:

        f.write("MOVIE_SAFE=1\n")
        f.write(
            f"RH3_TITLE={rh3['title']}\n"
        )
        f.write(
            f"MONEY_TITLE={money['title']}\n"
        )

        print()
        print(
            "Automatic map accepted:"
        )
        print(
            f"  Rush Hour 3 (2007) -> "
            f"Title {rh3['title']}"
        )
        print(
            f"  Money Talks (1997) -> "
            f"Title {money['title']}"
        )

    else:

        f.write("MOVIE_SAFE=0\n")
        f.write("RH3_TITLE=0\n")
        f.write("MONEY_TITLE=0\n")

        print()
        print(
            "SAFETY BLOCK: feature-title map "
            "was ambiguous."
        )
        print(
            "No movie rip will be started."
        )
PY

    if [[ -f "$MAP" ]]; then
        source "$MAP"
    fi

else

    echo "SAFETY BLOCK: completed raw VIDEO_TS was not found."

fi

###############################################################################
# RIP THE TWO MOVIES — NO JOB.JSON YET
###############################################################################

BURNER="/mnt/appdata/jarvis-burner-staging/local-bluray"

RH3_BUILD="$BURNER/.building-rush-hour-3-$STAMP"
MONEY_BUILD="$BURNER/.building-money-talks-$STAMP"

RH3_OK=1
MONEY_OK=1

rip_movie() {

    TITLE_NUMBER="$1"
    DISPLAY="$2"
    BUILD="$3"

    OUTDIR="$BUILD/$DISPLAY"
    OUTFILE="$OUTDIR/$DISPLAY.mkv"

    echo
    echo "================================================================"
    echo " RIPPING: $DISPLAY"
    echo " DVD title: $TITLE_NUMBER"
    echo "================================================================"

    if [[ -e "$BUILD" ]]; then
        echo "BLOCK: build path already exists:"
        echo "$BUILD"
        return 1
    fi

    mkdir -p "$OUTDIR"

    nice -n 10 \
        ionice -c2 -n7 \
        HandBrakeCLI \
          -i "$RAW_VTS" \
          -t "$TITLE_NUMBER" \
          -o "$OUTFILE" \
          --format av_mkv \
          -e x264 \
          -q 19 \
          -B 160

    RC=$?

    if [[ "$RC" -ne 0 ]]; then
        echo "RIP FAILED: HandBrake returned $RC"
        echo "Build data preserved at:"
        echo "$BUILD"
        return 1
    fi

    DUR="$(
        ffprobe \
          -v error \
          -show_entries format=duration \
          -of default=nw=1:nk=1 \
          "$OUTFILE" 2>/dev/null
    )"

    SIZE="$(
        stat -c%s "$OUTFILE" \
          2>/dev/null
    )"

    echo "Duration: ${DUR:-UNKNOWN} seconds"
    echo "Size:     ${SIZE:-UNKNOWN} bytes"

    if [[ -z "$DUR" || -z "$SIZE" ]]; then
        echo "RIP BLOCKED: ffprobe/stat verification failed."
        return 1
    fi

    if ! awk -v d="$DUR" \
        'BEGIN { exit !(d >= 4200) }'
    then
        echo "RIP BLOCKED: resulting runtime is below 70 minutes."
        return 1
    fi

    if [[ "$SIZE" -lt 200000000 ]]; then
        echo "RIP BLOCKED: resulting file is unexpectedly small."
        return 1
    fi

    echo "RIP VERIFIED: $DISPLAY"
    return 0
}

if [[ "$MOVIE_SAFE" -eq 1 ]]; then

    rip_movie \
      "$RH3_TITLE" \
      "Rush Hour 3 (2007)" \
      "$RH3_BUILD"

    RH3_OK=$?

    if [[ "$RH3_OK" -eq 0 ]]; then
        echo
        echo "===== 20-MINUTE THERMAL REST ====="
        echo "Rush Hour 3 raw encode completed."
        sleep 1200
    fi

    rip_movie \
      "$MONEY_TITLE" \
      "Money Talks (1997)" \
      "$MONEY_BUILD"

    MONEY_OK=$?

fi

###############################################################################
# PUBLISH COMPLETED MOVIES INTO EXISTING JARVIS MOVIE LANE
###############################################################################

publish_movie() {

    BUILD="$1"
    SLUG="$2"
    TITLE="$3"
    YEAR="$4"
    RATING="$5"

    DISPLAY="$TITLE ($YEAR)"
    JOBID="$SLUG-$STAMP"
    FINAL="$BURNER/$JOBID"
    MEDIA="$FINAL/$DISPLAY/$DISPLAY.mkv"

    echo
    echo "===== REGISTER WITH JARVIS ====="
    echo "$DISPLAY"

    if [[ ! -s "$BUILD/$DISPLAY/$DISPLAY.mkv" ]]; then
        echo "REGISTER BLOCKED: verified media file is missing."
        return 1
    fi

    if [[ -e "$FINAL" ]]; then
        echo "REGISTER BLOCKED: final job already exists:"
        echo "$FINAL"
        return 1
    fi

    mv -- "$BUILD" "$FINAL"

    python3 - \
      "$FINAL" \
      "$JOBID" \
      "$TITLE" \
      "$YEAR" \
      "$RATING" \
      "$DISPLAY" \
      "$RAW" <<'PY'
import json
import os
import sys
from datetime import datetime
from pathlib import Path

final = Path(sys.argv[1])
job_id = sys.argv[2]
title = sys.argv[3]
year = int(sys.argv[4])
rating = sys.argv[5]
display = sys.argv[6]
raw_source = sys.argv[7]

media = final / display / f"{display}.mkv"

payload = {
    "job_id": job_id,
    "job_type": "local-bluray",
    "media_type": "movie",
    "profile": "movie",
    "title": title,
    "year": year,
    "category": "General",
    "rating": rating,
    "state": "ready",
    "priority": 100,
    "source": "local_bluray",
    "source_path": str(final),
    "media_path": str(media),
    "raw_source_path": raw_source,
    "raw_source_preserved": True,
    "destination_root": "/mnt/media/Movies",
    "created_at": datetime.now().astimezone().isoformat(
        timespec="seconds"
    ),
    "source_metadata": {
        "lane": "local_bluray",
        "original_lane": "local_dvd_raw",
        "original_disc_label": "7000080254_1",
    },
}

temporary = final / ".job.json.tmp"
destination = final / "job.json"

temporary.write_text(
    json.dumps(payload, indent=2) + "\n",
    encoding="utf-8",
)

os.replace(
    temporary,
    destination,
)

print(destination)
PY

    echo "READY: $FINAL"
    return 0
}

REGISTERED=0

if [[ "$MOVIE_SAFE" -eq 1 ]]; then

    if [[ "$RH3_OK" -eq 0 ]]; then

        publish_movie \
          "$RH3_BUILD" \
          "rush-hour-3-2007" \
          "Rush Hour 3" \
          "2007" \
          "PG-13"

        if [[ "$?" -eq 0 ]]; then
            REGISTERED=$((REGISTERED + 1))
        fi

    fi

    if [[ "$MONEY_OK" -eq 0 ]]; then

        publish_movie \
          "$MONEY_BUILD" \
          "money-talks-1997" \
          "Money Talks" \
          "1997" \
          "R"

        if [[ "$?" -eq 0 ]]; then
            REGISTERED=$((REGISTERED + 1))
        fi

    fi

fi

###############################################################################
# GIVE CONTROL BACK TO THE EXISTING PRIORITY / COOLDOWN SYSTEM
###############################################################################

echo
echo "================================================================"
echo " RETURNING CONTROL TO JARVIS PRIORITY DISPATCHER"
echo "================================================================"

systemctl --user start "$TIMER" 2>/dev/null || true
TIMER_RESTORED=1

if [[ "$REGISTERED" -gt 0 ]]; then

    echo "Registered movie jobs: $REGISTERED"
    echo
    echo "Triggering first priority cycle."

    systemctl --user start --no-block "$SERVICE" \
      2>/dev/null || true

else

    echo "No new movie jobs were registered."
    echo "Priority timer was still restored."

fi

echo
echo "================================================================"
echo " OVERNIGHT HANDOFF COMPLETE"
echo " Finished staging/routing phase: $(date)"
echo
echo "Jarvis priority timer now owns READY movie processing."
echo "Its existing validation cooldown remains authoritative."
echo
echo "Raw DVD source was PRESERVED:"
echo "$RAW"
echo "================================================================"
