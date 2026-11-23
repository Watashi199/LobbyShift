#!/usr/bin/env bash
# LobbyShift uninstaller (native install). Docker users: docker compose down -v
#
#   sudo ./uninstall.sh           remove the app, keep VPN configs and settings
#   sudo ./uninstall.sh --purge   remove everything, including configs

set -euo pipefail

PURGE=false
[[ "${1:-}" == "--purge" ]] && PURGE=true

WG_IF=lobbyshift
TABLE=51820
PREF=5210

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }

[[ $EUID -eq 0 ]] || { echo -e "${RED}[ERROR]${NC} Run as root (sudo)"; exit 1; }

echo -e "${YELLOW}This removes the LobbyShift service, tunnel, firewall rules and program files.${NC}"
$PURGE && echo -e "${RED}--purge: VPN configs, settings and history are deleted too.${NC}"
read -r -p "Continue? (y/N): " answer
[[ "$answer" =~ ^[yY]$ ]] || { echo "Cancelled."; exit 0; }

# Service
systemctl disable --now lobbyshift 2>/dev/null || true
rm -f /etc/systemd/system/lobbyshift.service
systemctl daemon-reload
ok "Service removed"

# Tunnel and policy routing
while ip rule del pref "$PREF" 2>/dev/null; do :; done
ip route flush table "$TABLE" 2>/dev/null || true
ip link del dev "$WG_IF" 2>/dev/null || true
wg-quick down lobbyshift 2>/dev/null || true   # v1
rm -f /etc/wireguard/lobbyshift.conf
ok "Tunnel removed"

# Firewall
nft delete table inet lobbyshift 2>/dev/null || true
for bin in iptables iptables-legacy; do
    command -v "$bin" >/dev/null || continue
    "$bin" -S DOCKER-USER 2>/dev/null | grep -- '--comment lobbyshift' | sed 's/^-A/-D/' \
        | while read -r rule; do eval "$bin -w $rule" 2>/dev/null || true; done
    for table in nat filter; do   # v1 rules
        "$bin" -t "$table" -S 2>/dev/null | grep -- "lobbyshift-" | sed 's/^-A/-D/' \
            | while read -r rule; do eval "$bin -t $table $rule" 2>/dev/null || true; done
    done
done
if command -v netfilter-persistent >/dev/null; then
    netfilter-persistent save >/dev/null 2>&1 || true
fi
ok "Firewall rules removed"

# Files
rm -rf /opt/lobbyshift
rm -f /usr/local/bin/lobbyshift /etc/modules-load.d/lobbyshift.conf /etc/sysctl.d/99-lobbyshift.conf
warn "IP forwarding stays enabled until reboot (other services may rely on it)"
if $PURGE; then
    rm -rf /var/lib/lobbyshift /etc/lobbyshift /var/log/lobbyshift
    userdel lobbyshift 2>/dev/null || true
    ok "Configs, settings and service user removed"
else
    ok "Kept /var/lib/lobbyshift and /etc/lobbyshift (use --purge to delete them)"
fi

echo -e "\n${GREEN}LobbyShift has been uninstalled.${NC}"
