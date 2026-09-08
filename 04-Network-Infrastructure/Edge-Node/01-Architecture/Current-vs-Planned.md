# Current vs Planned

## Production now

- OpenVPN remote path to Alabama.
- Jellyfin Edge server.
- Home Assistant server and Media Command Center.
- Raw-disc/staging filesystem and confirmed-media cleanup.
- Proven Caleb → Jarvis raw-media workflow.
- Proven Jarvis → Caleb reverse-sync worker.
- Local Events dashboard and scheduled maintenance.
- Rust Node API telemetry service.
- Storage guard, health, maintenance and status tooling.

## Planned / backlog

- Expand Home Assistant from media/node telemetry into the full Tyler/Lindale severe-weather, camera and router-awareness role.
- Present combined catalog state more explicitly as Local / Jarvis-only / Available-to-sync / Processing.
- Add persistent storage-fault history directly to `node-status` so future USB/NVMe disconnects are obvious from one command.
- Reconcile the broader seven-day raw-retention design goal with the currently deployed 72-hour confirmed-transfer cleanup policy if a different retention tier is desired.
