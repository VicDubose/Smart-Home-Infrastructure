# Raw Disc Ingest

The Edge node exposes an optical drive at `/dev/sr0` and a dedicated 50 GiB staging filesystem.

Intended raw-disc flow:

1. Detect/inspect DVD or Blu-ray.
2. Burn/rip raw content into `/srv/staging/Raw_Rips`.
3. Place transfer-ready material into the transfer lifecycle.
4. Transfer the raw source across VPN to Jarvis.
5. Keep a local recovery copy until Jarvis receipt is confirmed.
6. Move confirmed local staging data into the retention/cleanup phase.

The raw staging filesystem is intentionally small to force a handoff-oriented workflow rather than permanent accumulation.
