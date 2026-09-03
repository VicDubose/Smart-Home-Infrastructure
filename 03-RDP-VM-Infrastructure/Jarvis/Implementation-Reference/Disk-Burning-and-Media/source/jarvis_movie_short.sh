#!/usr/bin/env bash

main() {
    SCRIPT="$HOME/rdp-scripts/Jarvis/media/jarvis_movie_dvd_ingest.py"

    HP_ID="/dev/disk/by-id/usb-hp_HLDS_DVDRW_GUD0N_423645525650343832373430-0:0"

    [[ -x "$(command -v python3)" ]] || {
        echo "❌ BLOCK: python3 unavailable"
        return 10
    }

    [[ -f "$SCRIPT" ]] || {
        echo "❌ BLOCK: movie pipeline missing"
        return 11
    }

    [[ $# -ge 2 ]] || {
        echo 'Usage: jarvis-movie "MOVIE TITLE" YEAR [extra Jarvis options]'
        echo 'Example: jarvis-movie "Fast & Furious Presents: Hobbs & Shaw" 2019 --dry-run'
        return 12
    }

    TITLE="$1"
    YEAR="$2"
    shift 2

    DVD="$(readlink -f "$HP_ID" 2>/dev/null || true)"

    [[ -b "$DVD" ]] || {
        echo "❌ BLOCK: HP DVD drive unavailable"
        return 13
    }

    echo "============================================================"
    echo " JARVIS MOVIE"
    echo "============================================================"
    echo "Drive: $DVD"
    lsblk -o NAME,SIZE,FSTYPE,LABEL,MODEL "$DVD"

    pgrep -x dvdbackup >/dev/null 2>&1 && {
        echo "❌ BLOCK: optical raw copy active"
        return 14
    }

    pgrep -f '[H]andBrakeCLI' >/dev/null 2>&1 && {
        echo "❌ BLOCK: HandBrake already active"
        return 15
    }

    SCAN="$(mktemp)"

    echo
    echo "Detecting complete DVD title count..."

    HandBrakeCLI -i "$DVD" -t 0 --scan >"$SCAN" 2>&1

    MAX="$(
        grep -Eo 'DVD has [0-9]+ title\(s\)' "$SCAN" |
        grep -Eo '[0-9]+' |
        sort -nr |
        head -1
    )"

    if [[ -z "$MAX" ]]; then
        echo "❌ BLOCK: could not determine DVD title count"
        rm -f "$SCAN"
        return 16
    fi

    echo "✅ DVD reports $MAX titles"

    rm -f "$SCAN"

    python3 "$SCRIPT" \
        --device "$DVD" \
        --title "$TITLE" \
        --year "$YEAR" \
        --ai phi3:mini \
        --max-title "$MAX" \
        "$@"
}

main "$@"
