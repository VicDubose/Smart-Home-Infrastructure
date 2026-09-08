# Storage / Jellyfin Recovery Runbook

If Jellyfin suddenly cannot play any files, do not immediately rebuild the container.

## Safe sequence

```bash
sudo systemctl stop caleb-edge-pull.service
docker stop jellyfin
sudo systemctl stop srv-media-External.automount
```

Then verify the expected UUID exists:

```bash
lsblk -o NAME,TRAN,TYPE,SIZE,FSTYPE,LABEL,UUID,MOUNTPOINTS,MODEL
sudo blkid | grep 'afeecb37-f7ee-4ebe-9c79-f495fb1e55ea'
```

If the device is absent, fix the physical USB/NVMe path before filesystem work.

If present and unmounted, perform an offline ext4 check against the UUID path. Do not mount/start Jellyfin while `e2fsck` is running.

After a clean verification pass:

1. start/trigger the automount,
2. verify the real ext4 layer is `rw`,
3. read-test several real media files,
4. inspect new kernel messages,
5. start Jellyfin only,
6. test actual playback,
7. start the Edge pull,
8. watch for transport errors under writes.

Any recurrence of device resets, offline errors or EXT4 aborts means the hardware path is not stable enough for set-and-forget use.
