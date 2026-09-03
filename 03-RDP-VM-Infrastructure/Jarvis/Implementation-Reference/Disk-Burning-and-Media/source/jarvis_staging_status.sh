#!/usr/bin/env bash
set -u

RAW="/mnt/appdata/arm/media/raw"
ARM_LOGS="/mnt/appdata/arm/logs"

summarize_root() {
    local path="$1"
    local label="$2"

    if [[ ! -d "$path" ]]; then
        printf "%-28s MISSING  %s\n" "$label" "$path"
        return
    fi

    local size files videos jobs
    size="$(du -sh "$path" 2>/dev/null | awk '{print $1}')"
    files="$(find "$path" -type f 2>/dev/null | wc -l)"
    videos="$(find "$path" -type f \( -iname '*.mkv' -o -iname '*.mp4' -o -iname '*.m4v' \) 2>/dev/null | wc -l)"
    jobs="$(find "$path" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)"

    printf "%-28s size=%-8s files=%-5s videos=%-5s jobs=%-4s %s\n" \
        "$label" "${size:-0}" "$files" "$videos" "$jobs" "$path"
}

echo "===== MEDIA STAGING ====="

summarize_root "/mnt/appdata/arm/media/raw"                         "ARM raw"
summarize_root "/mnt/appdata/arm/media/transcode"                   "ARM transcode"
summarize_root "/mnt/appdata/arm/media/completed"                   "ARM completed"
summarize_root "/mnt/appdata/arm/media/failed-hold"                  "ARM failed hold"
summarize_root "/mnt/appdata/jarvis-burner-staging/local-bluray"    "Jarvis Blu-ray"
summarize_root "/mnt/appdata/jarvis-burner-staging/local-dvd"       "Jarvis DVD"
summarize_root "/mnt/appdata/jarvis-burner-staging/local-dvd-raw"   "Jarvis DVD raw"
summarize_root "/mnt/appdata/jarvis-burner-staging/caleb-remote"    "Caleb remote"
summarize_root "/mnt/appdata/jarvis-validation-staging/active"      "Validation active"
summarize_root "/mnt/appdata/jarvis-validation-staging/review"      "Validation review"
summarize_root "/mnt/appdata/jarvis-validation-staging/blocked"     "Validation blocked"
summarize_root "/mnt/appdata/jarvis-validation-staging/rerip"       "Validation rerip"
summarize_root "/mnt/appdata/jarvis-validation-staging/finished"    "Validation finished"
summarize_root "/mnt/media/.jarvis-emergency-hold"                  "Emergency hold"

echo
echo "===== ARM RAW JOB CLASSIFICATION ====="

shopt -s nullglob
jobs=("$RAW"/*)

if (( ${#jobs[@]} == 0 )); then
    echo "No ARM raw jobs."
else
    ripping=0

    if pgrep -af '[m]akemkvcon|[H]andBrakeCLI|[d]vdbackup|[f]fmpeg' >/dev/null 2>&1; then
        ripping=1
    fi

    for job in "${jobs[@]}"; do
        [[ -d "$job" ]] || continue

        base="$(basename "$job")"
        container_path="/home/arm/media/raw/$base"

        files="$(find "$job" -type f 2>/dev/null | wc -l)"
        videos="$(find "$job" -type f \( -iname '*.mkv' -o -iname '*.mp4' -o -iname '*.m4v' \) 2>/dev/null | wc -l)"
        size="$(du -sh "$job" 2>/dev/null | awk '{print $1}')"

        newest_epoch="$(
            find "$job" -type f -printf '%T@\n' 2>/dev/null |
            sort -nr |
            head -1
        )"

        age_hours="?"
        recent=0

        if [[ -n "${newest_epoch:-}" ]]; then
            age_hours="$(
                awk -v now="$(date +%s)" -v then="$newest_epoch" \
                    'BEGIN { printf "%.1f", (now-then)/3600 }'
            )"

            if awk -v age="$age_hours" 'BEGIN { exit !(age < 0.25) }'; then
                recent=1
            fi
        fi

        mapfile -t logs < <(
            grep -RIlF -- "$container_path" "$ARM_LOGS" 2>/dev/null
        )

        failed=0

        if (( ${#logs[@]} > 0 )); then
            if grep -Ei \
                'Failed to save title|Call to MakeMKV failed|fatal error|Error while running MakeMKV' \
                "${logs[@]}" >/dev/null 2>&1
            then
                failed=1
            fi
        fi

        if (( failed == 1 )); then
            state="FAILED-CONFIRMED"
        elif (( ripping == 1 && recent == 1 )); then
            state="ACTIVE"
        elif (( files == 0 )); then
            state="EMPTY-ORPHAN"
        else
            state="STRANDED-REVIEW"
        fi

        printf "%-24s size=%-7s files=%-3s videos=%-3s age=%-7sh %s\n" \
            "$state" "${size:-0}" "$files" "$videos" "$age_hours" "$base"

        if (( ${#logs[@]} > 0 )); then
            printf "  Log: %s\n" "$(basename "${logs[0]}")"
        fi
    done
fi

echo
echo "Success requires an actual media file under ARM completed."
echo "FAILED-CONFIRMED is eligible for the controlled hold-and-cleanup workflow."
echo "STRANDED-REVIEW is never automatically deleted."
