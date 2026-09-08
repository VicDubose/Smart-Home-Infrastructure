# Current Known-Good State — 2026-09-07


| Component | Production state |
|---|---|
| Linux | Linux Mint 22.3 (Zena), Ubuntu Noble base |
| Kernel | 7.0.0-31-generic |
| Jellyfin | Running and healthy; HTTP 200 at release validation |
| Home Assistant | Running locally on port 8123 |
| Media SSD | `CALEB_EDGE_MEDIA`, mounted read/write at `/srv/media/External` |
| Staging | 50 GiB loop-backed ext4 at `/srv/staging` |
| VPN | OpenVPN tunnel to Alabama, `tun0` |
| Jarvis/Core | Reachable across VPN at `192.168.50.51` |
| Edge pull | `caleb-edge-pull.service`, production reverse-sync worker |
| Local Events | Dashboard + Sunday/Wednesday maintenance schedule |
| Node API | Rust/Axum telemetry service on port 8787 |
| Remote access | SSH + XRDP |


## Media recovery acceptance

The September 6 USB/NVMe incident was repaired by reseating the M.2 storage path and repairing the ext4 filesystem offline. Five independent media files passed direct read validation. Jellyfin was then restored and actual media playback worked again.

The final release check showed:

- `/srv/media/External` mounted ext4 read/write,
- Jellyfin `running` and `healthy`,
- Jellyfin public HTTP endpoint returning `200`,
- `caleb-edge-pull.service` active,
- an active reverse-sync download progressing steadily beyond 50%,
- no new kernel storage faults during the resumed write workload.

The node was therefore returned to frozen/set-and-forget production.
