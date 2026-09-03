#!/usr/bin/env bash
set -euo pipefail

EXPECTED_HOSTNAME="${EXPECTED_HOSTNAME:-caleb-HP-EliteBook-840-G7-Notebook-PC}"
SSH_USER="${SSH_USER:-caleb}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/caleb_reverse_sync}"
VPN_SUBNET_PREFIX="${VPN_SUBNET_PREFIX:-10.8.0}"

if [ ! -f "$SSH_KEY" ]; then
    echo "SSH key missing: $SSH_KEY" >&2
    exit 1
fi

export EXPECTED_HOSTNAME SSH_USER SSH_KEY VPN_SUBNET_PREFIX

find_candidate() {
    local host_number="$1"
    local ip="${VPN_SUBNET_PREFIX}.${host_number}"
    local result

    result="$(
        timeout 4 ssh \
            -i "$SSH_KEY" \
            -o BatchMode=yes \
            -o ConnectTimeout=2 \
            -o ConnectionAttempts=1 \
            -o StrictHostKeyChecking=no \
            -o UserKnownHostsFile=/dev/null \
            -o LogLevel=ERROR \
            "${SSH_USER}@${ip}" \
            'hostname' 2>/dev/null || true
    )"

    if [ "$result" = "$EXPECTED_HOSTNAME" ]; then
        printf '%s\n' "$ip"
    fi
}

export -f find_candidate

FOUND="$(
    seq 2 254 |
    xargs -P 32 -n 1 bash -c 'find_candidate "$1"' _ |
    head -1
)"

if [ -z "$FOUND" ]; then
    echo "Caleb laptop was not found on ${VPN_SUBNET_PREFIX}.0/24." >&2
    exit 1
fi

printf '%s\n' "$FOUND"
