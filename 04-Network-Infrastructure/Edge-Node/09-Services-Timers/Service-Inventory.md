# Service Inventory

| Unit | Purpose | Expected state |
|---|---|---|
| `caleb-edge-pull.service` | Reliable Jarvis/Core → Caleb media pull | active while populating; restart on failure |
| `caleb-edge-guard.service` | Cancel unsafe Jellyfin sync when health/mount/reserve fails | oneshot via timer |
| `caleb-edge-health.service` | Daily Edge health snapshot | oneshot via timer |
| `caleb-edge-maintenance.service` | Refresh discovery + start pull when safe | oneshot via timer |
| `caleb-node-api.service` | Local Rust telemetry API | enabled / persistent |
| `local-events-dashboard.service` | Local Events web board | enabled / persistent |
| `caleb-local-events-overnight.service` | Sunday/Wednesday maintenance | scheduled |
| `caleb-local-events-morning-release.service` | 06:00 resource release | scheduled |
| `caleb-local-events-expiry-cleanup.service` | Daily expired-event cleanup | scheduled |
| `caleb-staging-flush.service` | Confirmed staging retention cleanup | hourly timer |
| `caleb-jarvis-ai-tunnel.service` | Temporary localhost-only Jarvis AI forward | supporting/temporary |
