# Storage Layout

| Role | Device / source | Mount | Filesystem |
|---|---|---|---|
| System | internal NVMe partition | `/` | ext4 |
| EFI | internal NVMe EFI partition | `/boot/efi` | vfat |
| ARM / staging | `/var/lib/caleb-arm-staging.img` | `/srv/staging` | loop-backed ext4 |
| Edge media | UUID `afeecb37-f7ee-4ebe-9c79-f495fb1e55ea` | `/srv/media/External` | ext4 |

### Important rule: UUID, not `/dev/sdX`

The external media disk has appeared under different Linux block-device names across reconnects. Scripts and recovery procedures must treat the filesystem UUID and mountpoint as authoritative rather than assuming `/dev/sda1` or `/dev/sdb1`.

The production `/etc/fstab` entry uses systemd automount with finite device and mount timeouts and `nofail`.
