# Caleb Private Recovery Material

These items are intentionally NOT included in the GitHub-safe snapshot.

They may contain credentials, authentication state, encryption material,
API keys, or other secrets.

Keep private backups of:

- /etc/NetworkManager/system-connections/
- Home Assistant secrets.yaml
- Home Assistant authentication files under .storage/
- Home Assistant config entries containing integration credentials
- VPN credentials / certificates / private keys
- SSH private keys
- Jellyfin user/authentication state if exact account restoration is desired
- Any API-key files used by Caleb Node API or Local Events
- Any environment files (.env) containing credentials
- Any external service credentials used by Jarvis/Core communication

Do NOT commit those materials to GitHub.

The GitHub-safe snapshot plus these private credentials should be sufficient
to reconstruct Caleb on replacement hardware.
