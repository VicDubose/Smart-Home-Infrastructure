# Remote Access

Production remote-access services:

- SSH: TCP/22.
- XRDP: TCP/3389.
- OpenVPN route to Alabama.

Caleb can be administered remotely while normal application access remains local/VPN scoped.

Jarvis/Core privileges should remain narrower than local administrative privileges on Caleb itself. The Edge node needs local sudo/admin capability to operate Docker, filesystems and systemd; that does not imply unrestricted Alabama infrastructure access.
