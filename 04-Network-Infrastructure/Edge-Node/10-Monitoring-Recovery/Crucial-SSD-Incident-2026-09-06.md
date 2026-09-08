# Crucial Edge SSD Incident — 2026-09-06

## Symptom

Jellyfin remained up/healthy at the container level, but all media playback failed with fatal player errors. FFmpeg could not open real files because host storage had disappeared underneath the container.

## Failure chain

Kernel evidence showed the USB/NVMe device dropping during writes:

```text
USB reset / enumeration trouble
        -> error -71 / device not responding
        -> device offline write errors
        -> Buffer I/O errors
        -> JBD2 journal update failure
        -> EXT4 journal abort
        -> filesystem remounted read-only
        -> later device enumeration failure
        -> Jellyfin file I/O failures
```

The immediate failure was the USB transport/enclosure path, not a codec-specific Jellyfin failure.

## Recovery performed

1. Stop `caleb-edge-pull.service`.
2. Stop Jellyfin.
3. Stop media automount.
4. Verify the Edge SSD was not being enumerated.
5. Reseat the M.2/NVMe in the enclosure/dock.
6. Confirm RTL9210 + Crucial disk + expected filesystem UUID returned.
7. Run offline `e2fsck`; journal and free-space metadata were repaired.
8. Remount by UUID.
9. Read-test five separate media files.
10. Confirm no new kernel storage errors.
11. Start Jellyfin and validate playback.
12. Resume `caleb-edge-pull.service`.
13. Observe sustained download progress while checking the kernel journal.

## Release evidence

After recovery the Edge SSD was mounted ext4 read/write, Jellyfin was healthy with HTTP 200, and the pull worker advanced an active ~1.3 GiB episode past 50% with **no new storage faults**.
