# Jellyfin Container

Production container:

- Name: `jellyfin`
- Image: `jellyfin/jellyfin`
- Restart policy: `unless-stopped`
- Port: `8096`
- Snapshot health: `healthy`
- Snapshot HTTP check: `200`

Bind mounts:

```text
/srv/docker/jellyfin/config -> /config
/srv/docker/jellyfin/cache  -> /cache
/srv/media                  -> /media
```

ServerSync state database:

```text
/srv/docker/jellyfin/config/data/serversync/sync.db
```
