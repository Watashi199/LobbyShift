"""Proton VPN support.

Proton's server-list API is reserved to its authenticated official apps, so
LobbyShift works from the WireGuard configs users download from their
account (https://account.proton.me/u/0/vpn/WireGuard). Those files carry
metadata in comments that we exploit:

    [Interface]
    # Key for lobbyshift
    # NetShield = 0
    # Moderate NAT = on
    # NAT-PMP (Port Forwarding) = off
    # VPN Accelerator = on
    PrivateKey = ...
    Address = 10.2.0.2/32
    DNS = 10.2.0.1

    [Peer]
    # MX#12
    PublicKey = ...
    Endpoint = 1.2.3.4:51820

From that we derive the exit country (no GeoIP guess needed), the server
name, Secure Core routing and gaming-relevant advice.
"""

from __future__ import annotations

import re

from ..core.wgconfig import WgConfig

PROVIDER = "proton"
ACCOUNT_URL = "https://account.proton.me/u/0/vpn/WireGuard"

# Entry countries Proton uses for Secure Core ("CH-MX#1" = via CH, exit MX).
_SECURE_CORE_ENTRIES = {"CH", "IS", "SE"}
_SERVER_RE = re.compile(r"^(?P<a>[A-Z]{2})(?:-(?P<b>[A-Z]{2}))?(?:-[A-Z]+)?#(?P<num>\d+)\b")
_FEATURE_RE = re.compile(r"^(?P<key>[A-Za-z][A-Za-z0-9 ()-]*?)\s*=\s*(?P<value>.+)$")
_FEATURE_KEYS = {
    "netshield": "netshield",
    "moderate nat": "moderate_nat",
    "nat-pmp (port forwarding)": "port_forwarding",
    "vpn accelerator": "vpn_accelerator",
    "bouncing": "bouncing",
}


def server_info(cfg: WgConfig) -> dict | None:
    for comment in cfg.peer_comments:
        match = _SERVER_RE.match(comment.strip())
        if not match:
            continue
        a, b = match.group("a"), match.group("b")
        secure_core = bool(b) and a in _SECURE_CORE_ENTRIES
        exit_country = b if secure_core else a
        return {
            "server": comment.strip().split()[0],
            "exit_country": exit_country,
            "entry_country": a if secure_core else None,
            "secure_core": secure_core,
        }
    return None


def features(cfg: WgConfig) -> dict[str, str]:
    found: dict[str, str] = {}
    for comment in cfg.interface_comments:
        match = _FEATURE_RE.match(comment.strip())
        if match:
            key = _FEATURE_KEYS.get(match.group("key").strip().lower())
            if key:
                found[key] = match.group("value").strip().lower()
    return found


def matches(cfg: WgConfig) -> bool:
    if server_info(cfg):
        return True
    # Proton assigns every WireGuard client 10.2.0.2/32.
    return "10.2.0.2/32" in cfg.addresses and bool(features(cfg))


def advice(info: dict | None, feats: dict[str, str]) -> list[dict[str, str]]:
    tips: list[dict[str, str]] = []
    if feats.get("moderate_nat") == "off":
        tips.append({
            "level": "warning",
            "code": "moderate_nat_off",
            "message": "Moderate NAT is off: consoles may get a strict NAT type. "
                       "Regenerate the config with 'Moderate NAT' enabled.",
        })
    if info and info.get("secure_core"):
        tips.append({
            "level": "warning",
            "code": "secure_core",
            "message": "Secure Core server: traffic bounces through "
                       f"{info['entry_country']} first, which adds latency.",
        })
    if feats.get("netshield") not in (None, "0"):
        tips.append({
            "level": "info",
            "code": "netshield_on",
            "message": "NetShield is on. Only matchmaking traffic uses the tunnel, "
                       "so it brings nothing here; disable it if you see issues.",
        })
    if feats.get("vpn_accelerator") == "off":
        tips.append({
            "level": "info",
            "code": "accelerator_off",
            "message": "VPN Accelerator is off; enabling it usually lowers latency.",
        })
    return tips


def metadata(cfg: WgConfig) -> dict:
    info = server_info(cfg)
    feats = features(cfg)
    return {
        "server": info["server"] if info else None,
        "country": info["exit_country"] if info else None,
        "entry_country": info["entry_country"] if info else None,
        "secure_core": bool(info and info["secure_core"]),
        "features": feats,
        "advice": advice(info, feats),
    }
