# Network Topology

| Endpoint | Address / role |
|---|---|
| Caleb LAN | `192.168.1.20` at the snapshot |
| Caleb VPN | `10.8.0.6` on `tun0` |
| VPN peer | `10.8.0.5` |
| Jarvis/Core | `192.168.50.51` |

Observed Jarvis route:

```text
192.168.50.51 via 10.8.0.5 dev tun0 src 10.8.0.6
```

The LAN address is site-dependent and may change. The VPN relationship and Jarvis route are the important functional invariants.
