#!/usr/bin/env bash
# LobbyShift installer (native install with systemd).
# Supports Debian 12 (Bookworm) and 13 (Trixie), Ubuntu 22.04+, Raspberry Pi OS Bookworm or Trixie. Python >= 3.11.
# Prefer Docker? See docker-compose.yml.
#
# Re-running this script upgrades an existing install (v1 data is migrated).

set -euo pipefail

INSTALL_DIR=/opt/lobbyshift
CONFIG_DIR=/etc/lobbyshift
DATA_DIR=/var/lib/lobbyshift
SERVICE_USER=lobbyshift
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
fail()  { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

banner() {
    echo -e "${BLUE}"
    echo "╔═══════════════════════════════════════╗"
    echo "║         LobbyShift Installer          ║"
    echo "╚═══════════════════════════════════════╝"
    echo -e "${NC}"
}

check_system() {
    [[ $EUID -eq 0 ]] || fail "Run as root (sudo ./install.sh)"
    command -v apt-get >/dev/null || fail "Only apt-based systems are supported (use Docker otherwise)"
    command -v systemctl >/dev/null || fail "systemd is required"
}

install_dependencies() {
    info "Installing packages..."
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
        python3 python3-venv python3-pip iproute2 wireguard-tools nftables iputils-ping
    python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' \
        || fail "Python 3.11+ required (found $(python3 -V)). Use Docker on this system."
}

cleanup_v1() {
    # v1 ran wg-quick + an iptables script as root. Remove what it left behind;
    # its configs in $CONFIG_DIR are migrated by the new service on first start.
    if systemctl is-active --quiet lobbyshift; then
        info "Stopping running service..."
        systemctl stop lobbyshift
    fi
    if [[ -f /etc/wireguard/lobbyshift.conf ]]; then
        info "Removing v1 wg-quick setup..."
        wg-quick down lobbyshift 2>/dev/null || true
        rm -f /etc/wireguard/lobbyshift.conf
    fi
    if command -v iptables >/dev/null && iptables-save 2>/dev/null | grep -q "lobbyshift-"; then
        info "Removing v1 iptables rules..."
        for table in nat filter; do
            iptables -t "$table" -S 2>/dev/null | grep -- "lobbyshift-" | sed 's/^-A/-D/' \
                | while read -r rule; do eval "iptables -t $table $rule" 2>/dev/null || true; done
        done
        if command -v netfilter-persistent >/dev/null; then
            netfilter-persistent save >/dev/null 2>&1 || true
        fi
    fi
    rm -f "$CONFIG_DIR/iptables-rules.sh"
}

create_user() {
    if ! id "$SERVICE_USER" &>/dev/null; then
        info "Creating service user $SERVICE_USER..."
        useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
    fi
}

install_app() {
    info "Installing LobbyShift into $INSTALL_DIR..."
    rm -rf "$INSTALL_DIR"
    mkdir -p "$INSTALL_DIR"
    python3 -m venv "$INSTALL_DIR/venv"
    "$INSTALL_DIR/venv/bin/pip" install -q --upgrade pip
    "$INSTALL_DIR/venv/bin/pip" install -q "$SRC_DIR"
    ln -sf "$INSTALL_DIR/venv/bin/lobbyshift" /usr/local/bin/lobbyshift
}

write_config() {
    mkdir -p "$CONFIG_DIR"
    if [[ ! -f "$CONFIG_DIR/config.yaml" ]]; then
        install -m 0640 "$SRC_DIR/packaging/config.yaml.example" "$CONFIG_DIR/config.yaml"
    else
        info "Keeping existing $CONFIG_DIR/config.yaml"
    fi
    # The service user must read v1 configs (written by root in v1) to migrate them.
    chown -R "$SERVICE_USER:$SERVICE_USER" "$CONFIG_DIR"
    chmod 0750 "$CONFIG_DIR"
}

setup_host() {
    info "Enabling IP forwarding and the WireGuard module..."
    echo "net.ipv4.ip_forward=1" > /etc/sysctl.d/99-lobbyshift.conf
    sysctl -q -p /etc/sysctl.d/99-lobbyshift.conf
    echo wireguard > /etc/modules-load.d/lobbyshift.conf
    modprobe wireguard 2>/dev/null || warn "Could not load the wireguard module (a reboot may be needed)"
}

install_service() {
    info "Installing systemd service..."
    install -m 0644 "$SRC_DIR/packaging/lobbyshift.service" /etc/systemd/system/lobbyshift.service
    systemctl daemon-reload
    systemctl enable --now lobbyshift
}

print_success() {
    local ip password=""
    ip=$(hostname -I | awk '{print $1}')
    for _ in $(seq 1 20); do
        [[ -f "$DATA_DIR/initial-password" ]] && { password=$(cat "$DATA_DIR/initial-password"); break; }
        systemctl is-active --quiet lobbyshift || break
        sleep 0.5
    done

    echo ""
    echo -e "${GREEN}╔═══════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║        Installation complete          ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════╝${NC}"
    echo ""
    echo -e "Web interface: ${BLUE}http://$ip:8080${NC}"
    if [[ -n "$password" ]]; then
        echo -e "Admin password: ${YELLOW}$password${NC}  (change it in Settings)"
    else
        echo "Admin password: unchanged. Forgot it? sudo lobbyshift passwd"
    fi
    echo ""
    echo "Next steps:"
    echo "  1. Open the web interface and import your Proton VPN WireGuard configs"
    echo "  2. On the console: manual network settings, Gateway = $ip"
    echo "  3. Deploy a region and launch a match"
    echo ""
    echo "Check the setup: sudo lobbyshift doctor"
    systemctl is-active --quiet lobbyshift || warn "Service is not running: journalctl -u lobbyshift -e"
}

main() {
    banner
    check_system
    install_dependencies
    cleanup_v1
    create_user
    install_app
    write_config
    setup_host
    install_service
    print_success
}

main "$@"
