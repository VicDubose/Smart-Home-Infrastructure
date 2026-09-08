# Private Recovery Checklist — Never Commit These

The following materials must be stored in a secure private backup, not GitHub:

- `/etc/NetworkManager/system-connections/` profiles containing credentials.
- OpenVPN client profile, certificates and private keys.
- SSH private keys, including the Jarvis AI tunnel key.
- Home Assistant `secrets.yaml`.
- Home Assistant authentication storage and credential-bearing config entries.
- Caleb Node API `.env`.
- Jellyfin API/authentication secrets and user/account state where exact restoration is required.
- ServerSync or other plugin credentials.
- Local Events API keys/secrets/runtime credential files.
- Any `.env`, token, bearer, password or private-key material.
- The authoritative unredacted `caleb-edge-pull` source if authentication integration is embedded in source/config references.

After restoring a replacement device, rotate/revoke credentials if the old laptop was lost or compromised rather than merely failed.
