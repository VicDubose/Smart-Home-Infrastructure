# Health Checks

## Edge guard

Runs every five minutes and blocks/cancels unsafe ServerSync activity if Jellyfin is unhealthy, media filesystems are missing, or the configured free-space reserve is violated.

## Daily health

Records Jellyfin health, Core/VPN reachability, movie/episode counts and free-space figures.

## Maintenance

Twice monthly, maintenance verifies Jellyfin, VPN, Core, storage reserve and media mounts before refreshing ServerSync discovery and starting the reliable Edge pull.

## Persistent system journal

The host uses persistent journald storage, making kernel transport failures available after a reboot/reconnect event.
