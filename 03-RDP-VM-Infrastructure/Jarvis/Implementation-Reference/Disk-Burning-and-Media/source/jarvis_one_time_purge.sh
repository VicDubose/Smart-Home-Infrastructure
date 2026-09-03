#!/usr/bin/env bash
set -uo pipefail

main() {
    APP="/mnt/appdata"
    MEDIA="/mnt/media"
    RAW="$APP/jarvis-burner-staging/local-dvd-raw"
    STAGE="$APP/jarvis-burner-staging/local-dvd"
    EXPECTED_MEDIA_UUID="B6C41B77C41B38D7"

    declare -a SAFE_STAGE=()
    declare -a SAFE_RAW=()
    declare -a FAILED_REPLACED=()
    declare -a RECEIVING=()
    declare -a SAFE_RESCUE=()

    echo "============================================================"
    echo " JARVIS ONE-TIME PURGE"
    echo " SAFE / INTERACTIVE"
    echo "============================================================"

    echo
    echo "===== STORAGE BEFORE ====="
    df -h "$APP"
    echo
    du -sh "$RAW" "$STAGE" 2>/dev/null || true

    echo
    echo "===== MEDIA HDD SAFETY ====="

    SRC="$(findmnt -n -o SOURCE "$MEDIA" 2>/dev/null || true)"

    if [[ -z "$SRC" ]]; then
        echo "❌ BLOCK: /mnt/media is not mounted"
        return 10
    fi

    UUID="$(sudo blkid -s UUID -o value "$SRC" 2>/dev/null || true)"

    echo "Source: $SRC"
    echo "UUID:   $UUID"

    if [[ "$UUID" != "$EXPECTED_MEDIA_UUID" ]]; then
        echo "❌ BLOCK: expected Jellyfin HDD is not mounted"
        return 11
    fi

    [[ -d "$MEDIA/Shows" && -d "$MEDIA/Movies" ]] || {
        echo "❌ BLOCK: Jellyfin library structure missing"
        return 12
    }

    COUNT="$(
        find "$MEDIA" -type f \
          \( -iname '*.mkv' -o -iname '*.mp4' -o \
             -iname '*.avi' -o -iname '*.m4v' \) \
          2>/dev/null |
        wc -l
    )"

    echo "Media files: $COUNT"

    if [[ "$COUNT" -lt 20 ]]; then
        echo "❌ BLOCK: media HDD does not look populated"
        return 13
    fi

    echo "✅ Real Jellyfin HDD confirmed"

    echo
    echo "===== ACTIVE MEDIA WORK ====="

    if pgrep -af \
      '[H]andBrakeCLI|[d]vdbackup|[m]akemkvcon|[m]akemkv' \
      >/tmp/jarvis-purge-active.$$ 2>/dev/null
    then
        cat /tmp/jarvis-purge-active.$$
        rm -f /tmp/jarvis-purge-active.$$

        echo
        echo "❌ BLOCK: ripping/encoding is active"
        return 14
    fi

    rm -f /tmp/jarvis-purge-active.$$ 2>/dev/null || true

    echo "✅ No active rip/encode work"

    echo
    echo "============================================================"
    echo " 1. BYTE-IDENTICAL ENCODE STAGING"
    echo "============================================================"

    while IFS= read -r -d '' D; do
        mapfile -d '' FILES < <(
            find "$D" -type f \
              \( -iname '*.mkv' -o -iname '*.mp4' -o \
                 -iname '*.avi' -o -iname '*.m4v' \) \
              -print0 2>/dev/null
        )

        [[ "${#FILES[@]}" -gt 0 ]] || continue

        DIRSAFE=1

        for F in "${FILES[@]}"; do
            BASE="$(basename "$F")"
            FHASH="$(sha256sum "$F" | awk '{print $1}')"
            MATCH=0

            while IFS= read -r -d '' M; do
                MHASH="$(sha256sum "$M" | awk '{print $1}')"

                if [[ "$FHASH" == "$MHASH" ]]; then
                    MATCH=1
                    break
                fi
            done < <(
                find "$MEDIA" -type f -name "$BASE" -print0 2>/dev/null
            )

            if [[ "$MATCH" -ne 1 ]]; then
                DIRSAFE=0
                break
            fi
        done

        if [[ "$DIRSAFE" -eq 1 ]]; then
            SAFE_STAGE+=("$D")
            du -sh "$D"
        fi

    done < <(
        find "$STAGE" \
          -mindepth 1 -maxdepth 1 \
          -type d -print0 2>/dev/null
    )

    [[ "${#SAFE_STAGE[@]}" -gt 0 ]] ||
        echo "No byte-identical completed staging found."

    echo
    echo "============================================================"
    echo " 2. FAILED RAWS WITH CLEAN REPLACEMENTS"
    echo "============================================================"

    while IFS= read -r -d '' BAD; do
        NAME="$(basename "$BAD")"

        PREFIX="$(
            printf '%s\n' "$NAME" |
            sed -E \
              's/_[0-9]{8}-[0-9]{6}\.FAILED_READ_[0-9]{8}-[0-9]{6}$//'
        )"

        [[ "$PREFIX" != "$NAME" ]] || continue

        FOUND=0

        while IFS= read -r -d '' GOOD; do
            [[ "$GOOD" == "$BAD" ]] && continue
            [[ "$GOOD" == *.FAILED_READ_* ]] && continue
            [[ "$GOOD" == *.receiving ]] && continue

            if [[ -f "$GOOD/.rip_complete" ]]; then
                FOUND=1
                break
            fi
        done < <(
            find "$RAW" \
              -maxdepth 1 \
              -type d \
              -name "${PREFIX}_*" \
              -print0 2>/dev/null
        )

        if [[ "$FOUND" -eq 1 ]]; then
            FAILED_REPLACED+=("$BAD")
            du -sh "$BAD"
        fi

    done < <(
        find "$RAW" \
          -maxdepth 1 \
          -type d \
          -name '*.FAILED_READ_*' \
          -print0 2>/dev/null
    )

    [[ "${#FAILED_REPLACED[@]}" -gt 0 ]] ||
        echo "No replaceable failed raws found."

    echo
    echo "============================================================"
    echo " 3. VERIFIED RESCUE COPIES"
    echo "============================================================"

    while IFS= read -r -d '' R; do
        RSAFE=1
        RCNT=0

        while IFS= read -r -d '' F; do
            ((RCNT++))

            REL="${F#$R/}"
            DEST="$MEDIA/$REL"

            if [[ ! -f "$DEST" ]]; then
                RSAFE=0
                break
            fi

            A="$(sha256sum "$F" | awk '{print $1}')"
            B="$(sha256sum "$DEST" | awk '{print $1}')"

            if [[ "$A" != "$B" ]]; then
                RSAFE=0
                break
            fi
        done < <(
            find "$R" -type f -print0 2>/dev/null
        )

        if [[ "$RSAFE" -eq 1 && "$RCNT" -gt 0 ]]; then
            SAFE_RESCUE+=("$R")
            du -sh "$R"
        else
            echo "⚠️ PRESERVE: $(basename "$R")"
        fi

    done < <(
        find "$APP" \
          -maxdepth 1 \
          -type d \
          -name 'jarvis-media-rescue-*' \
          -print0 2>/dev/null
    )

    echo
    echo "============================================================"
    echo " 4. SAFE-MARKER RAWS"
    echo "============================================================"

    while IFS= read -r -d '' MARKER; do
        P="$(dirname "$MARKER")"

        [[ -f "$P/.jarvis_hold" ]] && continue
        [[ -f "$P/.jarvis_keep" ]] && continue
        [[ -f "$P/.jarvis_no_purge" ]] && continue

        [[ "$P" == *7000080254_1* ]] && continue

        SAFE_RAW+=("$P")
        du -sh "$P"

    done < <(
        find "$RAW" \
          -mindepth 2 \
          -maxdepth 2 \
          -name '.jarvis_safe_to_purge' \
          -print0 2>/dev/null
    )

    [[ "${#SAFE_RAW[@]}" -gt 0 ]] ||
        echo "No SAFE-marker raws."

    echo
    echo "============================================================"
    echo " 5. ABANDONED RECEIVING"
    echo "============================================================"

    while IFS= read -r -d '' P; do
        [[ "$P" == *7000080254_1* ]] && continue

        RECEIVING+=("$P")
        du -sh "$P"

    done < <(
        find "$RAW" \
          -maxdepth 1 \
          -type d \
          -name '*.receiving' \
          -print0 2>/dev/null
    )

    [[ "${#RECEIVING[@]}" -gt 0 ]] ||
        echo "No .receiving directories."

    echo
    echo "============================================================"
    echo " PROTECTED CONTENT"
    echo "============================================================"

    echo "Clean raw without SAFE marker: PRESERVED"
    echo ".jarvis_hold:                 PRESERVED"
    echo ".jarvis_keep:                 PRESERVED"
    echo ".jarvis_no_purge:             PRESERVED"
    echo "7000080254_1 mystery raw:     PRESERVED"
    echo "Non-identical rescue copies:  PRESERVED"
    echo "Emergency hold on HDD:        PRESERVED"
    echo "AI data:                      PRESERVED"
    echo "Caleb data:                   PRESERVED"

    echo
    echo "============================================================"
    echo " PRIMARY PURGE"
    echo "============================================================"

    echo "This deletes only:"
    echo " • byte-identical finished encode staging"
    echo " • failed raws with clean raw replacements"
    echo " • fully byte-identical rescue copies"
    echo

    PRIMARY_COUNT="$(
        printf '%s\n' \
          "${#SAFE_STAGE[@]}" \
          "${#FAILED_REPLACED[@]}" \
          "${#SAFE_RESCUE[@]}" |
        awk '{s+=$1} END {print s}'
    )"

    echo "Objects eligible: $PRIMARY_COUNT"

    if [[ "$PRIMARY_COUNT" -gt 0 ]]; then
        read -r -p "Type PURGE to perform primary cleanup: " A

        if [[ "$A" == "PURGE" ]]; then
            [[ "${#SAFE_STAGE[@]}" -gt 0 ]] &&
                sudo rm -rf -- "${SAFE_STAGE[@]}"

            [[ "${#FAILED_REPLACED[@]}" -gt 0 ]] &&
                sudo rm -rf -- "${FAILED_REPLACED[@]}"

            [[ "${#SAFE_RESCUE[@]}" -gt 0 ]] &&
                sudo rm -rf -- "${SAFE_RESCUE[@]}"

            sync
            echo "✅ Primary cleanup complete"
        else
            echo "Primary cleanup skipped."
        fi
    fi

    echo
    echo "============================================================"
    echo " OPTIONAL 7-DAY WAIVER"
    echo "============================================================"

    if [[ "${#SAFE_RAW[@]}" -gt 0 ]]; then
        echo "These raws already passed .jarvis_safe_to_purge."
        echo "This option waives whatever remains of the 7-day delay."
        echo

        read -r -p "Type PURGE7 to delete SAFE-marker raws now: " B

        if [[ "$B" == "PURGE7" ]]; then
            for P in "${SAFE_RAW[@]}"; do
                [[ "$P" == "$RAW/"* ]] || continue
                [[ -f "$P/.jarvis_safe_to_purge" ]] || continue
                [[ -f "$P/.jarvis_hold" ]] && continue
                [[ -f "$P/.jarvis_keep" ]] && continue
                [[ -f "$P/.jarvis_no_purge" ]] && continue
                [[ "$P" == *7000080254_1* ]] && continue

                echo "Deleting: $(basename "$P")"
                sudo rm -rf -- "$P"
            done

            sync
            echo "✅ SAFE-marker early purge complete"
        else
            echo "Normal 7-day retention remains intact."
        fi
    fi

    echo
    echo "============================================================"
    echo " OPTIONAL ABANDONED RECEIVING CLEANUP"
    echo "============================================================"

    if [[ "${#RECEIVING[@]}" -gt 0 ]]; then
        echo "These do NOT have clean raw-complete status."
        echo "Deleting them means those discs must be reripped."
        echo

        for P in "${RECEIVING[@]}"; do
            du -sh "$P"
        done

        echo
        read -r -p \
          "Type DROP_RECEIVING to discard all listed partial raws: " C

        if [[ "$C" == "DROP_RECEIVING" ]]; then
            sudo rm -rf -- "${RECEIVING[@]}"
            sync
            echo "✅ Abandoned receiving directories removed"
        else
            echo "Receiving directories preserved."
        fi
    fi

    echo
    echo "============================================================"
    echo " RECOVERY BIND-MOUNT HOUSEKEEPING"
    echo "============================================================"

    if mountpoint -q /mnt/jarvis-root-view; then
        if sudo umount /mnt/jarvis-root-view 2>/dev/null; then
            echo "✅ /mnt/jarvis-root-view unmounted"
        else
            echo "⚠️ /mnt/jarvis-root-view still busy — left mounted"
        fi
    else
        echo "✅ No recovery bind mount"
    fi

    echo
    echo "============================================================"
    echo " FINAL STORAGE"
    echo "============================================================"

    df -h "$APP"

    echo
    sudo du -xhd1 "$APP" 2>/dev/null | sort -h

    echo
    echo "✅ JARVIS ONE-TIME PURGE COMPLETE"

    return 0
}

main "$@"
