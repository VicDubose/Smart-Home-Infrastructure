# Local Events Architecture

- Dashboard service: `local-events-dashboard.service`.
- Bind: `0.0.0.0:8788`.
- Working directory: `/opt/local-events`.
- Web runtime: gunicorn.
- AI work can be routed temporarily through Jarvis using a scheduled SSH local-forward/tunnel rather than exposing Ollama publicly.

The production Local Events application remains a Caleb-local service even when an AI enrichment pass temporarily consumes Jarvis resources.
