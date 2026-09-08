#!/usr/bin/env bash

set +e

line() {
  printf '%*s\n' 72 '' | tr ' ' '='
}

section() {
  echo
  line
  echo " $1"
  line
}

service_state() {
  local service="$1"
  printf "%-22s enabled=%-10s active=%s\n" \
    "$service" \
    "$(systemctl is-enabled "$service" 2>/dev/null || echo unknown)" \
    "$(systemctl is-active "$service" 2>/dev/null || echo inactive)"
}

container_state() {
  local name="$1"

  if docker inspect "$name" >/dev/null 2>&1; then
    printf "%-18s status=%-12s health=%s\n" \
      "$name" \
      "$(docker inspect -f '{{.State.Status}}' "$name" 2>/dev/null)" \
      "$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}not-configured{{end}}' "$name" 2>/dev/null)"
  else
    printf "%-18s NOT FOUND\n" "$name"
  fi
}

clear

echo "CALEB REMOTE MEDIA NODE — SYSTEM STATUS"
echo "Generated: $(date)"
echo "Hostname:  $(hostname)"
echo "User:      $(whoami)"
echo "Uptime:    $(uptime -p)"
echo "Kernel:    $(uname -r)"

section "SYSTEM HEALTH"

echo "Load averages:"
uptime

echo
echo "CPU:"
lscpu | grep -E 'Model name|Socket|Core|Thread|CPU\(s\)' | head -10

echo
echo "Memory:"
free -h

echo
echo "Top memory users:"
ps -eo pid,comm,%cpu,%mem --sort=-%mem | head -8

echo
echo "Temperatures:"
if command -v sensors >/dev/null 2>&1; then
  sensors 2>/dev/null | grep -E 'Package id|Core [0-9]|Composite|temp[0-9]' | head -20
else
  echo "lm-sensors is not installed."
fi

section "FILESYSTEM STORAGE"

df -hT \
  -x tmpfs \
  -x devtmpfs \
  -x squashfs \
  -x overlay

echo
echo "Media and staging usage:"
du -sh /srv/media 2>/dev/null
du -sh /srv/staging 2>/dev/null
du -sh /srv/docker 2>/dev/null

section "EXTERNAL / USB / OPTICAL DRIVES"

echo "Block devices:"
lsblk -o NAME,TRAN,TYPE,SIZE,FSTYPE,LABEL,MOUNTPOINTS,MODEL

echo
echo "USB devices:"
lsusb 2>/dev/null || echo "lsusb unavailable."

echo
echo "Optical devices:"
if compgen -G "/dev/sr*" >/dev/null; then
  ls -lah /dev/sr*
  echo
  for drive in /dev/sr*; do
    echo "Drive: $drive"
    udevadm info --query=property --name="$drive" 2>/dev/null |
      grep -E 'ID_MODEL=|ID_VENDOR=|ID_CDROM=|ID_CDROM_MEDIA='
  done
else
  echo "No /dev/sr* optical drive detected."
fi

echo
echo "Mounted removable storage:"
findmnt -rn -o SOURCE,TARGET,FSTYPE,OPTIONS |
  grep -E '^/dev/(sd|sr|nvme|mmcblk)' || echo "No removable mounts detected."

section "NETWORK AND VPN"

echo "IP addresses:"
hostname -I

echo
echo "Active connections:"
nmcli connection show --active 2>/dev/null

echo
echo "VPN interface:"
ip -4 addr show tun0 2>/dev/null || echo "VPN is OFF."

echo
echo "Route to Jarvis:"
ip route get 192.168.50.51 2>/dev/null || echo "No route to Jarvis."

echo
echo "Jarvis connectivity:"
if ping -c 1 -W 2 192.168.50.51 >/dev/null 2>&1; then
  echo "Jarvis 192.168.50.51: REACHABLE"
else
  echo "Jarvis 192.168.50.51: UNREACHABLE"
fi

section "REMOTE ACCESS SERVICES"

service_state ssh
service_state xrdp
service_state xrdp-sesman
service_state docker

echo
echo "Listening remote-access ports:"
ss -lnt |
  awk 'NR==1 || /:22 |:3389 /'

section "DOCKER CONTAINERS"

if docker info >/dev/null 2>&1; then
  container_state jellyfin
  container_state homeassistant

  echo
  docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
else
  echo "Docker is active, but user $(whoami) cannot access the Docker socket."
  echo "Fix with: sudo usermod -aG docker $(whoami)"
fi

section "APPLICATION PORTS"

for port in 8096 8123; do
  if ss -lnt | grep -q ":${port} "; then
    echo "Port $port: LISTENING"
  else
    echo "Port $port: NOT LISTENING"
  fi
done

echo
echo "Local URLs:"
echo "Jellyfin:       http://localhost:8096"
echo "Home Assistant: http://localhost:8123"

VPN_IP="$(ip -4 -o addr show tun0 2>/dev/null | awk '{print $4}' | cut -d/ -f1)"

if [ -n "$VPN_IP" ]; then
  echo "VPN Jellyfin:       http://${VPN_IP}:8096"
  echo "VPN Home Assistant: http://${VPN_IP}:8123"
fi

section "RECENT SYSTEM FAILURES"

FAILED_UNITS="$(systemctl --failed --no-legend 2>/dev/null)"

if [ -n "$FAILED_UNITS" ]; then
  echo "$FAILED_UNITS"
else
  echo "No failed systemd units."
fi

echo
echo "Recent high-priority system messages:"
journalctl -p 0..3 -n 10 --no-pager 2>/dev/null ||
  echo "Unable to read system journal."

/usr/local/sbin/caleb-staging-status
section "FINAL SUMMARY"

SSH_STATE="$(systemctl is-active ssh 2>/dev/null)"
XRDP_STATE="$(systemctl is-active xrdp 2>/dev/null)"
DOCKER_STATE="$(systemctl is-active docker 2>/dev/null)"

echo "SSH:            $SSH_STATE"
echo "RDP:            $XRDP_STATE"
echo "Docker:         $DOCKER_STATE"

if docker inspect jellyfin >/dev/null 2>&1; then
  echo "Jellyfin:       $(docker inspect -f '{{.State.Status}}' jellyfin)"
else
  echo "Jellyfin:       unavailable"
fi

if docker inspect homeassistant >/dev/null 2>&1; then
  echo "Home Assistant: $(docker inspect -f '{{.State.Status}}' homeassistant)"
else
  echo "Home Assistant: unavailable"
fi

if compgen -G "/dev/sr*" >/dev/null; then
  echo "DVD drive:      detected"
else
  echo "DVD drive:      not detected"
fi

if ip link show tun0 >/dev/null 2>&1; then
  echo "VPN:            active"
else
  echo "VPN:            off"
fi

line
