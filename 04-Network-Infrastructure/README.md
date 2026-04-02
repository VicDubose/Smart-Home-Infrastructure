# 🌐 Home Network Architecture — Optimized Design

This network is designed to support a fully automated smart home system with high reliability, low latency, and efficient bandwidth utilization.

---

## 🎯 Design Goals

- Eliminate double NAT
- Centralize routing, firewall, and DHCP
- Maximize Wi-Fi performance using wired backhaul
- Allocate bandwidth intelligently across devices
- Maintain a simple, flat, and reliable LAN

---

## 🧱 Core Architecture

Internet → Bridged ISP Modem → ASUS Router → Mesh Node → Cisco Switch → Devices

---

## 🔌 Key Components

### ISP Gateway (Spectrum)
- Configured in **bridge mode**
- Functions only as a modem
- Passes public IP directly to ASUS router

### ASUS ZenWiFi Pro ET12 (Primary)
- Main router (NAT, DHCP, firewall)
- Handles all network intelligence
- Provides Wi-Fi 6E coverage
- DHCP range: 192.168.x.100–199

### ASUS ZenWiFi Pro ET12 (Node)
- Connected via **2.5G wired backhaul**
- Extends Wi-Fi coverage
- Acts as distribution point for wired devices

### Cisco Catalyst 2960-C (Layer 2)
- Provides wired connectivity
- Uplinked to mesh node (not primary router)
- Fast Ethernet ports used for low-bandwidth devices

---

## ⚡ Performance Strategy

- High-demand devices (Xbox, laptops) use **gigabit paths**
- Low-demand devices (HA, Eufy, IoT) use **100 Mbps ports**
- Wired backhaul ensures **stable Wi-Fi performance**
- Single flat subnet simplifies routing and automation

---

## 🔐 Security & Stability

- Single NAT boundary (ASUS router)
- No double NAT
- Centralized firewall enforcement
- DNS-over-TLS enabled
- No VLAN complexity (intentional design decision)

---

## 🧠 Design Philosophy

This network prioritizes:

- simplicity over unnecessary segmentation  
- performance through correct device placement  
- reliability through minimal failure points  

It is intentionally designed as a **single, efficient Layer 2 domain** with a strong Layer 3 edge.

---

## 🔗 Integration with Home Assistant

- Home Assistant operates entirely within the LAN
- No external exposure required
- All automations rely on stable internal routing
- Apple Home acts as the user-facing layer

---

## 📸 Physical Implementation

See `/screenshots` for real-world deployment:
- rack setup
- cable runs
- router placement
- modem configuration
