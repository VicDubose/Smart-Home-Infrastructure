# Node Role and Boundaries

## Caleb owns locally

- Jellyfin Edge playback and cache.
- Local 50 GiB raw-disc/staging workspace.
- External Edge media SSD.
- Home Assistant for local node/site awareness.
- Local Events Intelligence Board for Tyler/Lindale context.
- Node telemetry API and operational status commands.
- SSH/XRDP remote administration of the Caleb host.
- Optical-drive access for raw-disc ingestion.

## Jarvis/Core remains authoritative for

- Long-term media preservation.
- Media validation, identification, final naming and archive decisions.
- Shared-library authority.
- Higher-tier AI processing and orchestration.
- Durable copies when Caleb does not have sufficient local capacity.

## Explicit non-goals

Caleb is not the main Jarvis server, not a financial/control-plane node, not the authoritative shared-media archive, and not a permanent raw-disc archive.

## Capacity rule

A full Caleb media cache must not stop a valid ingest. Preserve the media on Jarvis first; Caleb can pull it back later when capacity allows.
