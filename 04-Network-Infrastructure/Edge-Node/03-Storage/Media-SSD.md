# Edge Media SSD

**Label:** `CALEB_EDGE_MEDIA`  
**UUID:** `afeecb37-f7ee-4ebe-9c79-f495fb1e55ea`  
**Mount:** `/srv/media/External`  
**Model:** Crucial `CT500P3SSD8`

This disk is Caleb's local playable-media cache. It is not the master library.

The reverse-sync worker enforces a **150 GiB free-space reserve** for its target media roots. When pulling another file would violate that reserve, the worker stops cleanly instead of filling the disk.

### Media namespace

Caleb exposes media to Jellyfin through `/srv/media`, including Movies and the external Shows hierarchy. Jellyfin sees `/srv/media` as `/media` inside the container.
