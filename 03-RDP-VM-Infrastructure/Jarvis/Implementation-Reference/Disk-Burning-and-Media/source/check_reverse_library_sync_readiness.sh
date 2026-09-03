#!/usr/bin/env bash

set -u
set -o pipefail

###############################################################################
# JARVIS ↔ CALEB REVERSE LIBRARY SYNC — READ-ONLY READINESS CHECK
#
# Run on Jarvis.
# This script makes no changes.
###############################################################################

CALEB_USER="${CALEB_USER:-caleb}"
CALEB_HOST="${CALEB_HOST:-10.8.0.6}"

JARVIS_MEDIA_ROOT="${JARVIS_MEDIA_ROOT:-/mnt/media}"
JARVIS_INCOMING="${JARVIS_INCOMING:-/mnt/appdata/caleb-media/reverse-incoming}"
JARVIS_REVIEW="${JARVIS_REVIEW:-/mnt/appdata/caleb-media/reverse-review}"

# Suspected locations only. The audit searches for the actual Caleb libraries.
CALEB_SEARCH_ROOTS=(
    "/srv"
    "/mnt"
    "/media"
    "/home/caleb"
)

REPORT_DIR="$HOME/Jarvis/reports/reverse-sync"
STAMP="$(date +%Y%m%d-%H%M%S)"
REPORT="$REPORT_DIR/reverse-sync-readiness-$STAMP.txt"

mkdir -p "$REPORT_DIR"

exec > >(tee "$REPORT") 2>&1

section() {
    echo
    echo "========================================================================"
    echo " $1"
    echo "========================================================================"
}

command_status() {
    local command_name="$1"

    if command -v "$command_name" >/dev/null 2>&1; then
        printf "%-18s PASS  %s\n" \
            "$command_name" \
            "$(command -v "$command_name")"
    else
        printf "%-18s MISSING\n" "$command_name"
    fi
}

section "REVERSE LIBRARY SYNC — READINESS AUDIT"

echo "Generated:  $(date --iso-8601=seconds)"
echo "Jarvis:     $(hostname)"
echo "Caleb SSH:  ${CALEB_USER}@${CALEB_HOST}"
echo "Mode:       READ ONLY"
echo "Report:     $REPORT"

###############################################################################
# JARVIS
###############################################################################

section "JARVIS — IDENTITY AND NETWORK"

hostnamectl 2>/dev/null | sed -n '1,12p' || hostname
echo
ip -brief address 2>/dev/null || true
echo
ip route 2>/dev/null || true

section "JARVIS — REQUIRED COMMANDS"

for cmd in \
    ssh \
    rsync \
    python3 \
    find \
    sha256sum \
    b2sum \
    ffprobe \
    ffmpeg \
    jq \
    flock \
    timeout \
    systemctl \
    docker
do
    command_status "$cmd"
done

section "JARVIS — ACTIVE MEDIA OR TRANSFER PROCESSES"

ACTIVE_JARVIS="$(
    pgrep -af \
    'HandBrakeCLI|ffmpeg|ffprobe|dvdbackup|makemkv|MakeMKV|rsync|rclone|scp|jarvis_disc|jarvis_caleb|process_caleb' \
    2>/dev/null |
    grep -vE \
    'pgrep|check_reverse_library_sync_readiness|REVERSE LIBRARY SYNC' \
    || true
)"

if [[ -n "$ACTIVE_JARVIS" ]]; then
    echo "BUSY:"
    echo "$ACTIVE_JARVIS"
else
    echo "PASS: No active Jarvis media-processing or transfer job."
fi

section "JARVIS — STORAGE"

df -hT / "$JARVIS_MEDIA_ROOT" /mnt/appdata 2>/dev/null || true

echo
echo "Jarvis media usage:"
du -sh "$JARVIS_MEDIA_ROOT" 2>/dev/null || true

echo
echo "Jarvis show/movie directory sizes:"
find "$JARVIS_MEDIA_ROOT" \
    -mindepth 1 \
    -maxdepth 2 \
    -type d \
    -print0 2>/dev/null |
while IFS= read -r -d '' folder; do
    du -sh "$folder" 2>/dev/null
done |
sort -h |
tail -40

section "JARVIS — FILESYSTEM AND DESTINATION SAFETY"

for path in \
    "$JARVIS_MEDIA_ROOT" \
    "/mnt/appdata" \
    "$JARVIS_INCOMING" \
    "$JARVIS_REVIEW"
do
    echo
    echo "Path: $path"

    if [[ -e "$path" ]]; then
        stat -c \
            'Exists: yes%nType: %F%nOwner: %U:%G%nPermissions: %A%nFilesystem device: %d' \
            "$path" 2>/dev/null || true

        if [[ -d "$path" && -w "$path" ]]; then
            echo "Writable by onsiteadmin: yes"
        elif [[ -d "$path" ]]; then
            echo "Writable by onsiteadmin: no"
        fi
    else
        echo "Exists: no"
        echo "NOTE: This audit will not create it."
    fi
done

echo
echo "Mount checks:"
findmnt "$JARVIS_MEDIA_ROOT" 2>/dev/null || true
findmnt /mnt/appdata 2>/dev/null || true

section "JARVIS — JELLYFIN"

if docker ps \
    --format '{{.Names}}' 2>/dev/null |
    grep -qx 'jellyfin'
then
    echo "Container: running"

    docker inspect jellyfin \
        --format '{{range .Mounts}}{{println .Source " -> " .Destination}}{{end}}' \
        2>/dev/null || true

    echo
    echo "Health:"
    docker inspect jellyfin \
        --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}not-configured{{end}}' \
        2>/dev/null || true
else
    echo "Container named jellyfin is not currently running."
fi

echo
echo "Jarvis library file totals:"

printf "Video files: "
find "$JARVIS_MEDIA_ROOT" \
    -type f \
    \( \
        -iname '*.mkv' -o \
        -iname '*.mp4' -o \
        -iname '*.m4v' -o \
        -iname '*.avi' \
    \) 2>/dev/null |
wc -l

printf "Total media bytes: "
find "$JARVIS_MEDIA_ROOT" \
    -type f \
    \( \
        -iname '*.mkv' -o \
        -iname '*.mp4' -o \
        -iname '*.m4v' -o \
        -iname '*.avi' \
    \) \
    -printf '%s\n' 2>/dev/null |
awk '{total += $1} END {printf "%.2f GiB\n", total / 1073741824}'

section "JARVIS — EXISTING REVERSE-SYNC FILES"

find \
    "$HOME/rdp-scripts/Jarvis" \
    "$HOME/Jarvis" \
    -maxdepth 5 \
    -type f \
    \( \
        -iname '*reverse*sync*' -o \
        -iname '*manifest*' -o \
        -iname '*library*sync*' \
    \) \
    -printf '%TY-%Tm-%Td %TH:%TM  %p\n' 2>/dev/null |
sort

###############################################################################
# CALEB CONNECTIVITY
###############################################################################

section "CALEB — VPN AND SSH CONNECTIVITY"

if ping -c 2 -W 2 "$CALEB_HOST" >/dev/null 2>&1; then
    echo "Ping: PASS — $CALEB_HOST responds."
else
    echo "Ping: no response."
    echo "This can still work when ICMP is blocked; testing SSH next."
fi

if timeout 5 bash -c \
    "exec 3<>/dev/tcp/$CALEB_HOST/22" 2>/dev/null
then
    echo "SSH port 22: PASS"
else
    echo "SSH port 22: FAIL"
    echo
    echo "Cannot continue the remote Caleb inspection."
    echo "Confirm his VPN address and SSH service."
    echo
    echo "Report saved: $REPORT"
    exit 1
fi

echo
echo "The following remote section may ask for Caleb's SSH password."

###############################################################################
# CALEB REMOTE AUDIT
###############################################################################

section "CALEB — REMOTE READ-ONLY AUDIT"

ssh \
    -o ConnectTimeout=10 \
    -o ServerAliveInterval=15 \
    -o ServerAliveCountMax=2 \
    "${CALEB_USER}@${CALEB_HOST}" \
    'bash -s' <<'REMOTE'
set -u
set -o pipefail

section() {
    echo
    echo "------------------------------------------------------------------------"
    echo "$1"
    echo "------------------------------------------------------------------------"
}

command_status() {
    local command_name="$1"

    if command -v "$command_name" >/dev/null 2>&1; then
        printf "%-18s PASS  %s\n" \
            "$command_name" \
            "$(command -v "$command_name")"
    else
        printf "%-18s MISSING\n" "$command_name"
    fi
}

section "IDENTITY"

echo "Hostname: $(hostname)"
echo "User:     $(id)"
echo "Time:     $(date --iso-8601=seconds)"
echo
hostnamectl 2>/dev/null | sed -n '1,12p' || true

section "NETWORK AND VPN"

ip -brief address 2>/dev/null || true
echo
ip route 2>/dev/null || true

echo
echo "VPN interfaces:"
ip -brief address 2>/dev/null |
grep -E 'tun|tap|wg|tailscale' \
|| echo "No obvious VPN interface detected."

echo
echo "OpenVPN processes:"
pgrep -af 'openvpn|NetworkManager.*vpn' 2>/dev/null \
|| echo "No OpenVPN process detected."

echo
echo "OpenVPN services:"
systemctl --type=service \
    --state=running \
    --no-pager 2>/dev/null |
grep -Ei 'openvpn|vpn' \
|| echo "No system OpenVPN service shown."

systemctl --user --type=service \
    --state=running \
    --no-pager 2>/dev/null |
grep -Ei 'openvpn|vpn' \
|| true

section "REQUIRED COMMANDS"

for cmd in \
    rsync \
    ssh \
    python3 \
    find \
    sha256sum \
    b2sum \
    ffprobe \
    ffmpeg \
    jq \
    flock \
    timeout \
    systemctl \
    docker
do
    command_status "$cmd"
done

section "ACTIVE RIP, INGEST, OR TRANSFER JOBS"

ACTIVE="$(
    pgrep -af \
    'HandBrakeCLI|ffmpeg|ffprobe|dvdbackup|makemkv|MakeMKV|rsync|rclone|scp|rip_and_send|auto_dvd_ingest|jarvis' \
    2>/dev/null |
    grep -vE 'pgrep|bash -s' \
    || true
)"

if [[ -n "$ACTIVE" ]]; then
    echo "BUSY:"
    echo "$ACTIVE"
else
    echo "PASS: No active media processing or transfer."
fi

section "DISK AND 250 GB STORAGE GUARD"

df -hT / /srv /mnt /media 2>/dev/null || true

echo
echo "Large top-level media-related directories:"

for root in /srv /mnt /media /home/caleb; do
    [[ -d "$root" ]] || continue

    find "$root" \
        -mindepth 1 \
        -maxdepth 2 \
        -type d \
        -print0 2>/dev/null
done |
while IFS= read -r -d '' folder; do
    du -sx --block-size=1 "$folder" 2>/dev/null
done |
sort -n |
tail -40 |
awk '{
    bytes=$1
    $1=""
    sub(/^ /, "", $0)
    printf "%.2f GiB  %s\n", bytes/1073741824, $0
}'

section "JELLYFIN CONTAINER AND MOUNTS"

if docker ps \
    --format '{{.Names}}' 2>/dev/null |
    grep -qx 'jellyfin'
then
    echo "Container: running"

    echo
    echo "Jellyfin mounts:"
    docker inspect jellyfin \
        --format '{{range .Mounts}}{{println .Source " -> " .Destination}}{{end}}' \
        2>/dev/null || true

    echo
    echo "Jellyfin health:"
    docker inspect jellyfin \
        --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}not-configured{{end}}' \
        2>/dev/null || true
else
    echo "No running Docker container named jellyfin."

    echo
    echo "Possible Jellyfin processes:"
    pgrep -af jellyfin 2>/dev/null \
    || echo "No Jellyfin process found."
fi

section "POSSIBLE JELLYFIN MEDIA LIBRARIES"

# Avoid application caches, Docker internals, raw-rip staging and metadata.
for root in /srv /mnt /media /home/caleb; do
    [[ -d "$root" ]] || continue

    find "$root" \
        -type f \
        \( \
            -iname '*.mkv' -o \
            -iname '*.mp4' -o \
            -iname '*.m4v' -o \
            -iname '*.avi' \
        \) \
        ! -path '/srv/staging/Raw_Rips/*' \
        ! -path '*/docker/*' \
        ! -path '*/.cache/*' \
        ! -path '*/jellyfin/config/*' \
        ! -path '*/jellyfin/cache/*' \
        -printf '%h\n' 2>/dev/null
done |
sort |
uniq -c |
sort -nr |
head -60

section "MEDIA TOTALS BY LIKELY ROOT"

for path in \
    /srv/media \
    /srv/jellyfin/media \
    /srv/docker/jellyfin/media \
    /mnt/media \
    /media \
    /home/caleb/Videos
do
    [[ -d "$path" ]] || continue

    count="$(
        find "$path" \
            -type f \
            \( \
                -iname '*.mkv' -o \
                -iname '*.mp4' -o \
                -iname '*.m4v' -o \
                -iname '*.avi' \
            \) 2>/dev/null |
        wc -l
    )"

    bytes="$(
        find "$path" \
            -type f \
            \( \
                -iname '*.mkv' -o \
                -iname '*.mp4' -o \
                -iname '*.m4v' -o \
                -iname '*.avi' \
            \) \
            -printf '%s\n' 2>/dev/null |
        awk '{total += $1} END {print total + 0}'
    )"

    printf "%-40s %6s files  %8.2f GiB\n" \
        "$path" \
        "$count" \
        "$(awk -v value="$bytes" 'BEGIN {print value/1073741824}')"
done

section "RAW-RIP STAGING — KEPT SEPARATE FROM JELLYFIN"

if [[ -d /srv/staging/Raw_Rips/DVD ]]; then
    du -sh /srv/staging/Raw_Rips/DVD 2>/dev/null || true

    printf "Raw-rip folders: "
    find /srv/staging/Raw_Rips/DVD \
        -mindepth 1 \
        -maxdepth 1 \
        -type d 2>/dev/null |
    wc -l
else
    echo "Raw-rip staging path not found."
fi

section "CURRENT SYSTEMD TIMERS"

systemctl list-timers \
    --all \
    --no-pager 2>/dev/null |
grep -Ei 'jarvis|jellyfin|vpn|openvpn|sync|rip' \
|| echo "No matching system timers."

echo
systemctl --user list-timers \
    --all \
    --no-pager 2>/dev/null |
grep -Ei 'jarvis|jellyfin|vpn|openvpn|sync|rip' \
|| echo "No matching user timers."

section "EXISTING REVERSE-SYNC FILES"

find \
    /srv/jarvis \
    /home/caleb \
    -maxdepth 5 \
    -type f \
    \( \
        -iname '*reverse*sync*' -o \
        -iname '*manifest*' -o \
        -iname '*library*sync*' \
    \) \
    -printf '%TY-%Tm-%Td %TH:%TM  %p\n' 2>/dev/null |
sort

section "CALEB AUDIT COMPLETE"
REMOTE

SSH_RESULT=$?

###############################################################################
# FINAL
###############################################################################

section "PRELIMINARY RESULT"

if [[ "$SSH_RESULT" -eq 0 ]]; then
    echo "PASS: Caleb remote inspection completed."
else
    echo "REVIEW: Caleb remote inspection returned code $SSH_RESULT."
fi

echo
echo "No files were transferred."
echo "No media was deleted."
echo "No services were changed."
echo "No directories were created on Caleb."
echo
echo "Readiness report:"
echo "$REPORT"

section "AUDIT COMPLETE"
