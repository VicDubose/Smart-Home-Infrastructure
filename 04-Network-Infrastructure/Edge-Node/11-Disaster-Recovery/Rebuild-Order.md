# Rebuild Order

1. Install Linux Mint/Ubuntu-compatible Linux.
2. Create the local `caleb` administrative user and hostname as desired.
3. Install Docker, OpenSSH, XRDP, Python tooling, Rust toolchain/runtime dependencies and required system packages.
4. Recreate `/srv/docker`, `/srv/media`, `/srv/staging` and application directories.
5. Recreate the 50 GiB loop-backed staging filesystem and permanent staging directory structure.
6. Attach/format the Edge media SSD and mount it by UUID at `/srv/media/External`.
7. Restore media namespace/symlinks expected by Jellyfin and Edge tooling.
8. Restore Jellyfin config/state from the private backup or recreate the container using the documented binds.
9. Restore Home Assistant config/state from the private backup or recreate its host-network container.
10. Restore the Caleb Node API binary/source and private `.env`.
11. Restore `/opt/local-events` application and its private runtime configuration.
12. Install the sanitized systemd units, replacing placeholders with private credential paths/users where required.
13. Restore operational scripts (`node-status`, Edge guard/health/maintenance/status/staging tooling, and the authoritative Edge pull source).
14. Restore OpenVPN profile/certificates privately.
15. Restore SSH private keys privately.
16. Enable only the production timers/services documented in `09-Services-Timers`.
17. Keep the old Friday VPN timers disabled.
18. Validate VPN route to Jarvis.
19. Validate Jellyfin HTTP and real media reads.
20. Validate Home Assistant and Node API telemetry.
21. Validate Local Events dashboard and timer schedule.
22. Validate raw-disc staging and Jarvis handoff.
23. Validate reverse sync while watching storage reserve and kernel logs.
24. Run `node-status` and the acceptance checklist before declaring the replacement frozen.
