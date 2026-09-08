# Hardware Inventory

| Component | Production observation |
|---|---|
| Platform | HP EliteBook 840-series laptop |
| CPU | Intel Core i5-1145G7, 4 cores / 8 threads, up to 4.4 GHz |
| Memory | ~15 GiB usable in the live snapshot |
| Internal system disk | 476.9 GiB NVMe (`MTFDKBA512TFH-1BC1AABHA`) |
| Edge media disk | Crucial `CT500P3SSD8`, 465.8 GiB USB-attached NVMe/SSD |
| NVMe bridge | Realtek RTL9210 M.2 NVMe adapter, UAS, 10 Gbit/s link observed |
| Ethernet | Realtek RTL8153 USB Gigabit Ethernet adapter |
| Optical drive | HP `DVDRAM GT31L`, exposed as `/dev/sr0` |
| Dock / enclosure | UGREEN Revodok NVMe 10-in-1 docking station currently used for the Edge-storage/dock role |

The USB/NVMe path is operationally important because the September 2026 outage originated at the transport/enclosure path rather than Jellyfin itself.
