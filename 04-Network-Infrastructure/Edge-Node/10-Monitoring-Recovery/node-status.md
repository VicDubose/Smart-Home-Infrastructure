# `node-status`

`/usr/local/bin/node-status` is the primary human-readable node summary. It reports:

- load, CPU, memory and temperature,
- filesystem/storage utilization,
- USB/optical devices,
- network/VPN and route to Jarvis,
- SSH/XRDP/Docker state,
- Jellyfin/Home Assistant container state,
- application ports,
- recent high-priority journal messages,
- ARM/staging state and cleanup timer,
- final service summary.

## Planned storage-history extension

The next maintenance revision should add a dedicated Media SSD Health section that searches the persistent journal for recent:

- USB disconnect/reset/descriptor failures,
- UAS/SCSI transport errors,
- `device offline`,
- buffer I/O errors,
- JBD2 journal aborts,
- EXT4 remount-read-only events,
- UUID/mount failures.

The September 2026 incident proved this belongs in the normal status path, but the production node was frozen before adding another live change.
