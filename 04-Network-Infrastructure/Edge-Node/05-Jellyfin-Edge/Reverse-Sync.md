# Jarvis → Caleb Reverse Sync

Production worker: `caleb-edge-pull.service`  
Executable: `/usr/local/sbin/caleb-edge-pull`

The worker consumes ServerSync discovery rows and downloads content from Jarvis/Core into Caleb's media cache.

Key behaviors observed in the production source:

- `series-at-a-time-v2` ordering for shows.
- Existing complete files are recognized as `PRESENT`.
- `.part` files can resume interrupted transfers.
- Non-bonus interrupted episodes receive priority.
- Bonus/extras are intentionally ordered after normal seasons.
- Downloads use retries and byte-range resume behavior.
- A completed `.part` file is atomically renamed into place.
- The worker stops before violating the 150 GiB reserve.
- The systemd unit requires `/srv/media/External` and runs an explicit mountpoint pre-check.
- On failure, systemd retries after five minutes.

The original working script may contain authentication integration that is intentionally not reproduced verbatim in public-safe documentation. See the private recovery checklist.
