# Application Ports and Routes

| Port | Service |
|---:|---|
| 22 | SSH |
| 3389 | XRDP |
| 8096 | Jellyfin |
| 8123 | Home Assistant |
| 8787 | Caleb Node API |
| 8788 | Local Events Intelligence Board |
| 11435 | Temporary local-forward endpoint used by the Jarvis AI tunnel when active |

The temporary AI tunnel forwards a localhost-only port toward Jarvis Ollama during scheduled Local Events AI work. Credentials and the private-key path are not stored in this repository.
