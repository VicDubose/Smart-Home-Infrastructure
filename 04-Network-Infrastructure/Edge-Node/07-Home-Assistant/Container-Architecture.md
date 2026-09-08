# Home Assistant Container Architecture

Production characteristics:

- Container: `homeassistant`.
- Image: `ghcr.io/home-assistant/home-assistant:stable`.
- Network mode: host.
- Restart policy: `unless-stopped`.
- Host configuration: `/srv/docker/homeassistant` → `/config`.
- HTTP: port `8123`.

The Mobile App integration has been enabled explicitly. The system does not rely on the broad `default_config` bundle solely to make the app work.
