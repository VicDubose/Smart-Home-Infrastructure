# Node Telemetry

Home Assistant polls the local Caleb Node API at `http://127.0.0.1:8787/api/status` on a 30-second interval.

The API aggregates node, storage, network/VPN, Docker, Jellyfin, ingest and recent-error state. HA template sensors then expose that state to dashboards and automations.

The API is backed by a Rust/Axum systemd service. Authentication secrets are supplied outside the public repository.
