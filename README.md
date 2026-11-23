# 🎯 LOBBYSHIFT

```
██╗      ██████╗ ██████╗ ██████╗ ██╗   ██╗███████╗██╗  ██╗██╗███████╗████████╗
██║     ██╔═══██╗██╔══██╗██╔══██╗╚██╗ ██╔╝██╔════╝██║  ██║██║██╔════╝╚══██╔══╝
██║     ██║   ██║██████╔╝██████╔╝ ╚████╔╝ ███████╗███████║██║█████╗     ██║   
██║     ██║   ██║██╔══██╗██╔══██╗  ╚██╔╝  ╚════██║██╔══██║██║██╔══╝     ██║   
███████╗╚██████╔╝██████╔╝██████╔╝   ██║   ███████║██║  ██║██║██║        ██║   
╚══════╝ ╚═════╝ ╚═════╝ ╚═════╝    ╚═╝   ╚══════╝╚═╝  ╚═╝╚═╝╚═╝        ╚═╝   
```

<p align="center">
  <strong>▶ TACTICAL MATCHMAKING CONTROL SYSTEM ◀</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/STATUS-OPERATIONAL-brightgreen?style=for-the-badge" alt="Status">
  <img src="https://img.shields.io/badge/PLATFORM-RPI%20%7C%20UBUNTU%20%7C%20DEBIAN-blue?style=for-the-badge" alt="Platform">
  <img src="https://img.shields.io/badge/LICENSE-CC%20BY--NC%204.0-orange?style=for-the-badge" alt="License">
</p>

<p align="center">
  <a href="#-mission-briefing">Mission Briefing</a> •
  <a href="#-tactical-features">Features</a> •
  <a href="#-deployment">Deployment</a> •
  <a href="#-field-manual">Field Manual</a> •
  <a href="#-intel">Intel</a>
</p>

---

## 📋 MISSION BRIEFING

**CLASSIFICATION:** Public Release  
**OPERATION:** Matchmaking Optimization  
**TARGET:** SBMM-Protected Lobbies

LobbyShift is a **self-hosted tactical VPN gateway** designed to intercept and reroute Call of Duty matchmaking traffic through global server nodes. This allows operatives to access alternative matchmaking regions while maintaining optimal combat latency.

**PRIMARY OBJECTIVES:**
- ✅ Bypass regional matchmaking restrictions
- ✅ Maintain low-latency gameplay connections
- ✅ Zero subscription fees
- ✅ Full operational security (self-hosted)

> *"Why pay for services when you can deploy your own?"*

---

## ⚡ TACTICAL FEATURES

| SYSTEM | CAPABILITY |
|--------|------------|
| 🌍 **Region Switching** | Deploy to any VPN node with one click |
| 🎯 **Split Tunneling** | Only matchmaking traffic (185.34.0.0/16, configurable) is rerouted |
| ⚡ **Low Latency** | Game traffic stays direct – zero impact on ping |
| 📶 **Latency Scan** | Measure the ping of every region before deploying |
| 🛡️ **Proton VPN Intel** | Server, Secure Core and NAT settings read from your Proton configs, with tuning advice |
| 🎮 **Per-Device Routing** | Choose which consoles use the VPN (or the whole LAN) |
| 🚫 **Kill Switch** | Optional: block matchmaking instead of leaking it direct when the VPN drops |
| 🔁 **Watchdog** | Detects a dead tunnel and reconnects automatically |
| 🖥️ **Command Center** | Military-grade web interface with timezone intel |
| ⭐ **Quick Deploy** | Pin favorite regions for rapid switching |
| 📜 **Operation Log** | Track all connection history |
| 🌐 **Offline GeoIP** | Country flags from a local database: no lookups sent to third parties |
| 🕹️ **Multi-Platform** | PS5, Xbox Series X\|S, PC compatible |
| 🔒 **OPSEC** | Password-protected UI, no root process, configs can't run commands |
| 🐳 **Docker or Native** | `docker compose up -d` or the classic installer |
| 🏷️ **Custom Names** | Rename regions (e.g. "Bot Lobbies" instead of "mx-free-47") |
| 🚀 **Autostart** | Auto-connect to preferred region on boot |

---

## 🌐 LANGUAGE SUPPORT

| FLAG | LANGUAGE | STATUS |
|------|----------|--------|
| 🇬🇧 **English** | Default Language | ACTIVE |
| 🇩🇪 **Deutsch** | German | ACTIVE |
| 🇫🇷 **Français** | French | ACTIVE |
| 🇮🇹 **Italiano** | Italian | ACTIVE |
| 🇪🇸 **Español** | Spanish | ACTIVE |

> Language selector deployed in top-right corner. Preference persists in browser storage.

---

## 🔧 SYSTEM ARCHITECTURE

```
                         ┌─────────────────────────────────────┐
                         │         LOBBYSHIFT GATEWAY          │
                         │        ┌─────────────────┐          │
┌──────────────┐         │        │   WEB COMMAND   │          │
│    PS5 /     │         │        │     CENTER      │          │
│   XBOX /     │────────▶│        │    :8080        │          │
│     PC       │         │        └────────┬────────┘          │
└──────────────┘         │                 │                   │
   Gateway:              │    ┌────────────┴────────────┐      │
   192.168.1.x           │    ▼                         ▼      │
                         │ ┌──────┐              ┌──────────┐  │
                         │ │DIRECT│              │ WIREGUARD│  │
                         │ │ROUTE │              │  TUNNEL  │  │
                         │ └──┬───┘              └────┬─────┘  │
                         │    │                       │        │
                         └────┼───────────────────────┼────────┘
                              │                       │
                              ▼                       ▼
                    ┌─────────────────┐    ┌─────────────────┐
                    │  REGULAR TRAFFIC │    │ COD MATCHMAKING │
                    │  YouTube, etc.   │    │  185.34.0.0/16  │
                    │     ↓            │    │       ↓         │
                    │   INTERNET       │    │  VPN SERVER     │
                    │                  │    │  (MX/TR/JP...)  │
                    └─────────────────┘    └─────────────────┘
```

**TRAFFIC FLOW:**
1. Console/PC designates LobbyShift as network gateway
2. Standard traffic → Direct route to internet
3. CoD matchmaking IPs → Encrypted tunnel to VPN node
4. Matchmaking server sees VPN location → Alternative region lobbies
5. Game server connection → Direct route → Minimal latency

<details>
<summary>▶ UNDER THE HOOD</summary>

- The tunnel is built directly with `ip link` + `wg setconf`, **not** `wg-quick`: only
  cryptographic keys are loaded from your config, so `PostUp`/`PreUp` lines (which would run
  shell commands) and `DNS` are ignored.
- **Policy routing**: matchmaking ranges live in a dedicated routing table (`51820`), selected by
  an `ip rule` matching your consoles' source address. Everything else falls through to the main
  table and goes out directly. The gateway host's own traffic is never affected.
- **nftables**: one `inet lobbyshift` table (NAT, MSS clamping, optional kill switch), replaced
  atomically on every change.
- The service runs as an unprivileged user with only `CAP_NET_ADMIN` and `CAP_NET_RAW`.
- Restarting the service (or upgrading) keeps the tunnel up: consoles are not disconnected.

</details>

---

## 📋 SYSTEM REQUIREMENTS

**HARDWARE:**
- Raspberry Pi 4+ (recommended)
- Any Ubuntu/Debian server
- Minimum 1GB RAM

**SOFTWARE:**
- Native install: Debian 13 Trixie (recommended) or 12 Bookworm / Ubuntu 22.04+ /
  Raspberry Pi OS Trixie or Bookworm (Python 3.11+)
- Or any Linux with Docker (amd64, arm64, armv7)
- Kernel with WireGuard (5.6+, standard on all of the above)
- WireGuard-compatible VPN subscription

**SUPPORTED VPN PROVIDERS:**

| Provider | Free Tier | Recommended |
|----------|-----------|-------------|
| [ProtonVPN](https://protonvpn.com) | ✅ Yes | ⭐ Best for beginners |
| [Mullvad](https://mullvad.net) | ❌ No | ⭐ Best privacy |
| [IVPN](https://ivpn.net) | ❌ No | Good alternative |
| [Windscribe](https://windscribe.com) | ✅ Limited | Budget option |
| and more... |

---

## 🗺️ REGIONAL INTELLIGENCE

| REGION | CODE | DIFFICULTY | PROTONVPN |
|--------|------|------------|-----------|
| 🇲🇽 Mexico | MX | 🟢 Easy | **Free** ✓ |
| 🇹🇷 Turkey | TR | 🟢 Easy | Plus |
| 🇪🇬 Egypt | EG | 🟢 Easy | Plus |
| 🇿🇦 South Africa | ZA | 🟢 Easy | Plus |
| 🇯🇵 Japan | JP | 🟡 Medium | **Free** ✓ |
| 🇳🇱 Netherlands | NL | 🟡 Medium | **Free** ✓ |
| 🇧🇷 Brazil | BR | 🟡 Medium | Plus |
| 🇦🇷 Argentina | AR | 🟢 Easy | Plus |
| 🇺🇸 USA | US | 🔴 Hard | **Free** ✓ |

> **INTEL:** ProtonVPN Free provides access to Japan, Netherlands, USA, and Mexico. Sufficient for initial operations.

---

## 🚀 DEPLOYMENT

### Option A: Native Install (Recommended for Raspberry Pi)

```bash
# Clone repository
git clone https://github.com/Smokimcpot/LobbyShift.git
cd LobbyShift

# Execute deployment
sudo ./install.sh
```

The installer prints the web address and a generated **admin password** at the end.

**DEPLOYMENT CHECKLIST:**
- ✅ WireGuard tools, nftables, Python environment
- ✅ IP forwarding + WireGuard module on boot
- ✅ Hardened systemd service running as the unprivileged `lobbyshift` user
- ✅ `lobbyshift` CLI
- ✅ **Upgrading from v1?** Just run it again: your configs, custom names, favorites, history
  and autostart are migrated automatically, and the old iptables rules are removed.

### Option B: Docker

```bash
# Host prerequisites (once)
echo 'net.ipv4.ip_forward=1' | sudo tee /etc/sysctl.d/99-lobbyshift.conf && sudo sysctl --system
echo wireguard | sudo tee /etc/modules-load.d/lobbyshift.conf && sudo modprobe wireguard

# Run
git clone https://github.com/Smokimcpot/LobbyShift.git && cd LobbyShift
docker compose up -d
docker compose logs lobbyshift | grep -i password   # generated admin password
```

The container uses the host network (it *is* the consoles' gateway) and only gets the
`NET_ADMIN` and `NET_RAW` capabilities. Settings can be passed as `LOBBYSHIFT_*` environment
variables in `docker-compose.yml`. LobbyShift detects Docker's `FORWARD DROP` policy and
whitelists your LAN in the `DOCKER-USER` chain automatically.

### Configuration

Static settings live in `/etc/lobbyshift/config.yaml` (see
[`packaging/config.yaml.example`](packaging/config.yaml.example)): LAN interface/subnet
(auto-detected by default), routed ranges, web port. Everything else is set in the web UI.

### Clean Uninstall

```bash
cd LobbyShift
sudo ./uninstall.sh            # keeps your VPN configs and settings
sudo ./uninstall.sh --purge    # removes everything
# Docker: docker compose down -v
```

---

## 📖 FIELD MANUAL

### 1. Access Command Center

```
http://<SERVER-IP>:8080
```

<p align="center">
  <img src="docs/images/webui.png" alt="LobbyShift Web Interface" width="800">
</p>

Log in with the admin password shown at install time (change it under **Settings**).

### 2. Upload VPN Configs

1. Acquire WireGuard configs from VPN provider
2. Access LobbyShift web interface
3. Drag & drop `.conf` files (or a `.zip` of them) to the upload zone
4. System auto-configures split tunneling
5. Click **Measure latency** to compare regions

#### Proton VPN

Download configs from **[account.proton.me → VPN → WireGuard](https://account.proton.me/u/0/vpn/WireGuard)**,
one per server you want, with these options:

| OPTION | VALUE | WHY |
|--------|-------|-----|
| Platform | Router | Plain config, no extras |
| NetShield | Off | Only matchmaking uses the tunnel, it brings nothing |
| **Moderate NAT** | **On** | Better NAT type on consoles |
| VPN Accelerator | On | Lower latency |
| Port forwarding | Off | Not needed |
| Secure Core | Off | Adds a hop, more latency |

LobbyShift reads the server name (`MX#12`, `CH-JP#3`...) and options embedded in each file:
the country is exact (no GeoIP guess), Secure Core servers are tagged, and a warning appears
if a config was generated with settings that hurt gaming (e.g. Moderate NAT off).

> Proton's server list API is reserved for its official apps, so LobbyShift works from the
> configs you download: that keeps your Proton credentials out of it.

### 3. Configure Console

#### PLAYSTATION 5

| PARAMETER | VALUE |
|-----------|-------|
| IP Address | Automatic |
| Subnet Mask | `255.255.255.0` |
| **Gateway** | **LobbyShift Server IP** |
| DNS Primary | Router IP or `8.8.8.8` |
| DNS Secondary | `1.1.1.1` |

**PATH:** Settings → Network → Set Up Internet Connection → Advanced Settings

#### XBOX SERIES X|S

| PARAMETER | VALUE |
|-----------|-------|
| IP Address | Keep current |
| Subnet Mask | `255.255.255.0` |
| **Gateway** | **LobbyShift Server IP** |
| DNS Primary | `8.8.8.8` |
| DNS Secondary | `1.1.1.1` |

**PATH:** Settings → General → Network Settings → Advanced Settings → IP Settings

#### PC

**PATH:** Network Settings → Change Adapter Options → Properties → IPv4  
**SET:** Default Gateway → LobbyShift Server IP

### 4. Deploy Region

1. Select target region in Command Center
2. Click **[DEPLOY]**
3. **RESTART GAME** for changes to take effect
4. Engage easier lobbies

### 5. Optional Settings

- **Devices**: list your consoles' IPs so only they use the VPN (default: the whole LAN).
  Give them a DHCP reservation on your router so the IP never changes.
- **Kill switch**: if the tunnel drops, block matchmaking instead of letting it go direct.
- **Auto-reconnect**: the watchdog rebuilds a tunnel that stopped handshaking.
- **Autostart**: deploy a region automatically at boot.

---

## ⌨️ CLI OPERATIONS

```bash
sudo lobbyshift status            # tunnel state, health, traffic
sudo lobbyshift list              # regions (* active, + favorite) with latency
sudo lobbyshift connect mexico    # deploy region (alias: switch)
sudo lobbyshift up                # reconnect last region
sudo lobbyshift down              # disconnect
sudo lobbyshift latency           # measure all regions
sudo lobbyshift doctor            # check the host setup
sudo lobbyshift passwd            # reset the admin password

journalctl -u lobbyshift -f       # live logs
# Docker: docker compose exec lobbyshift lobbyshift status
```

`sudo` is needed to read the local API token in `/var/lib/lobbyshift`.

---

## 🔌 API ENDPOINTS

All endpoints except `/api/health` and `/api/auth/*` require authentication: the session
cookie set by `POST /api/auth/login`, or `Authorization: Bearer <token>` with the token stored
in `/var/lib/lobbyshift/cli-token`. Cross-origin writes are refused.

```bash
TOKEN=$(sudo cat /var/lib/lobbyshift/cli-token)
curl -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/status
```

### Tunnel

| ENDPOINT | METHOD | OPERATION |
|----------|--------|-----------|
| `/api/status` | GET | Tunnel state, health, traffic, LAN, problems |
| `/api/tunnel/connect/{name}` | POST | Deploy region |
| `/api/tunnel/up` | POST | Reconnect last region |
| `/api/tunnel/down` | POST | Disconnect |
| `/api/latency` | POST | Measure latency (`{"names": [...]}` or all) |

### Regions

| ENDPOINT | METHOD | OPERATION |
|----------|--------|-----------|
| `/api/configs` | GET | List regions |
| `/api/configs` | POST | Upload `.conf` / `.zip` (multipart field `files`) |
| `/api/configs/{name}` | GET | Region + config text (private key hidden) |
| `/api/configs/{name}/text` | PUT | Replace config text (`[HIDDEN]` keeps the key) |
| `/api/configs/{name}` | PATCH | `display_name`, `favorite` |
| `/api/configs/{name}` | DELETE | Remove region |
| `/api/providers/proton` | GET | Proton setup help and stats |

### Settings & System

| ENDPOINT | METHOD | OPERATION |
|----------|--------|-----------|
| `/api/settings` | GET | Preferences, devices, routed ranges, LAN |
| `/api/settings/prefs` | PUT | `autostart`, `autostart_config`, `kill_switch`, `auto_reconnect` |
| `/api/settings/devices` | PUT | Consoles routed through the VPN |
| `/api/auth/password` | PUT | Change admin password |
| `/api/events` | GET / DELETE | Operation history |
| `/api/system/doctor` | GET | Host checks |
| `/api/system/geoip/update` | POST | Refresh the GeoIP database |
| `/api/health` | GET | Liveness (public) |

---

## ❓ INTEL (FAQ)

<details>
<summary><strong>▶ Compatible with Warzone 2026/MW3/Black Ops 6?</strong></summary>

**AFFIRMATIVE.** LobbyShift is compatible with all Call of Duty titles utilizing the 185.34.0.0/16 matchmaking range.

</details>

<details>
<summary><strong>▶ Risk of account termination?</strong></summary>

**LOW RISK.** VPN usage technically violates Activision ToS. However, detection is rare. Thousands of operatives use VPN services daily. Recommend using secondary account for operations.

</details>

<details>
<summary><strong>▶ High latency issues?</strong></summary>

**CHECK:** Only the matchmaking ranges go through the tunnel, whatever `AllowedIPs` your
provider put in the config (LobbyShift ignores it). Use **Measure latency** to pick a closer
server, and avoid Proton Secure Core servers (they add a hop).

</details>

<details>
<summary><strong>▶ Multi-device support?</strong></summary>

**AFFIRMATIVE.** By default, any device using LobbyShift as gateway has its CoD traffic routed
through the VPN. Add devices under **Settings → Devices** to restrict it to specific consoles.

</details>

<details>
<summary><strong>▶ VPN subscription required?</strong></summary>

**NEGATIVE.** ProtonVPN Free provides servers in Japan, Netherlands, USA, Mexico. Sufficient for initial operations. Plus subscription unlocks additional regions.

</details>

<details>
<summary><strong>▶ Flags not showing correctly?</strong></summary>

Proton configs get their country from the server name. For other providers, the country comes
from the offline DB-IP database, downloaded on first start: click **Update GeoIP database** in
Settings → System check if the server had no internet access at that moment.

</details>

<details>
<summary><strong>▶ Forgot the admin password?</strong></summary>

`sudo lobbyshift passwd` (Docker: `docker compose exec lobbyshift lobbyshift passwd`).

</details>

<details>
<summary><strong>▶ What changed in v2? Is it safe to upgrade?</strong></summary>

v2 is a rewrite focused on security and reliability: login-protected UI, no root process,
configs can no longer execute commands, nftables instead of iptables scripts, Docker image.
Re-running `install.sh` migrates all your v1 data. The HTTP API changed (see above), so
update any script that called the v1 endpoints.

</details>

---

## 🛠️ TROUBLESHOOTING

### First Step: Run the Doctor

```bash
sudo lobbyshift doctor     # or Settings → System check in the web UI
```

It checks LAN detection, IP forwarding, `ip`/`wg`/`nft`, the WireGuard module, the firewall
table and the GeoIP database.

### No Internet After Gateway Configuration

```bash
# Verify IP forwarding
cat /proc/sys/net/ipv4/ip_forward  # Should output: 1

# Check the gateway rules
sudo nft list table inet lobbyshift
```

**Docker installed on the gateway?** Docker sets the `FORWARD` policy to `DROP`. LobbyShift adds
`ACCEPT` rules for your LAN to the `DOCKER-USER` chain automatically; check them with
`sudo iptables -L DOCKER-USER -n`. A firewall such as `ufw` must also allow forwarding
(`DEFAULT_FORWARD_POLICY="ACCEPT"` in `/etc/default/ufw`).

### VPN Connection Failure

```bash
# WireGuard status (look at "latest handshake")
sudo wg show lobbyshift

# Policy routing
ip rule show | grep 51820
ip route show table 51820

# Live logs
sudo journalctl -u lobbyshift -f
```

No handshake usually means a revoked/expired key: download a fresh config from your provider.

### Web Interface Unavailable

```bash
# Service check
sudo systemctl status lobbyshift

# Port verification
sudo ss -tlnp | grep 8080
```

### Network Interface Keeps Disconnecting (Link Up/Down)

**SYMPTOM:** Severe lag, Discord disconnects, SSH drops. Check with:

```bash
sudo dmesg | grep -i "link is"
# If you see repeated "NIC Link is Down" / "NIC Link is Up" messages, 
# this is a power management issue.
```

**CAUSE:** Network card power management (Wake-on-LAN, Energy Efficient Ethernet) causes instability under load.

**QUICK FIX:**

```bash
# Disable Wake-on-LAN (replace eno1 with your interface)
sudo ethtool -s eno1 wol d

# Disable Energy Efficient Ethernet (if supported)
sudo ethtool --set-eee eno1 eee off 2>/dev/null

# Verify
sudo ethtool eno1 | grep -i "wake\|speed\|link"
```

> **NOTE:** Find your interface name with `ip link show`

**PERMANENT FIX (survives reboot):**

```bash
# Create systemd service
sudo tee /etc/systemd/system/nic-powersave-off.service << 'EOF'
[Unit]
Description=Disable NIC Power Management
After=network.target

[Service]
Type=oneshot
ExecStart=/sbin/ethtool -s eno1 wol d
ExecStart=/sbin/ethtool --set-eee eno1 eee off

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable nic-powersave-off
sudo systemctl start nic-powersave-off
```

**AFFECTED HARDWARE:** Common on Intel NICs (e1000e driver), especially on HP EliteDesk, Dell OptiPlex, and similar business PCs.

### Flags Not Showing (Globe Icon 🌍)

Settings → System check → **Update GeoIP database**, or:

```bash
TOKEN=$(sudo cat /var/lib/lobbyshift/cli-token)
curl -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8080/api/system/geoip/update
```

---

## 🤝 CONTRIBUTING

Contributions welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**AREAS OF INTEREST:**
- 🌐 Additional VPN provider integrations
- 🌍 Additional language localizations
- 🧪 Testing on more hardware

IP geolocation by [DB-IP](https://db-ip.com) (CC BY 4.0).

---

## ⚠️ DISCLAIMER

```
THIS SOFTWARE IS PROVIDED FOR EDUCATIONAL PURPOSES ONLY.

Using VPNs to manipulate matchmaking may violate game Terms of Service.
The developers assume no responsibility for account penalties or bans.

OPERATE AT YOUR OWN RISK.
```

---

## 📄 LICENSE

**Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)**

| PERMITTED | PROHIBITED |
|-----------|------------|
| ✅ Personal use | ❌ Commercial use |
| ✅ Modification | ❌ Selling software |
| ✅ Distribution | ❌ Paid services |

See [LICENSE](LICENSE) for full terms.

---

## ⭐ SUPPORT THE MISSION

If this project provided value, consider leaving a ⭐

---

<p align="center">
  <strong>━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━</strong>
</p>

<p align="center">
  Made with ❤️ by <a href="https://github.com/Smokimcpot">Smokimcpot</a>
</p>

<p align="center">
  <strong>▶ LOBBYSHIFT v2.0 ◀</strong>
</p>
