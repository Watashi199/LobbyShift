"""Host network discovery and sysctl helpers."""

from __future__ import annotations

import ipaddress
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .runner import Runner

log = logging.getLogger(__name__)

SYSCTL_ROOT = Path("/proc/sys")


@dataclass(frozen=True)
class LanInfo:
    interface: str
    subnet: str
    address: str


class NetworkError(RuntimeError):
    pass


async def detect_lan(runner: Runner, interface: str = "", subnet: str = "") -> LanInfo:
    """Find the LAN interface (default route) and its IPv4 subnet."""
    if not interface:
        res = await runner.run("ip", "-j", "-4", "route", "show", "default", check=False)
        routes = _json(res.stdout)
        if not routes:
            raise NetworkError("No IPv4 default route: set lan_interface in config.yaml")
        interface = routes[0].get("dev", "")
        if not interface:
            raise NetworkError("Default route has no interface")

    res = await runner.run("ip", "-j", "-4", "addr", "show", "dev", interface, check=False)
    links = _json(res.stdout)
    addr_info = [a for link in links for a in link.get("addr_info", []) if a.get("family") == "inet"]
    if not addr_info:
        raise NetworkError(f"Interface {interface} has no IPv4 address")
    address = addr_info[0]["local"]
    if not subnet:
        subnet = str(ipaddress.IPv4Interface(f"{address}/{addr_info[0]['prefixlen']}").network)
    return LanInfo(interface=interface, subnet=subnet, address=address)


def _json(text: str) -> list[dict]:
    try:
        data = json.loads(text or "[]")
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def read_sysctl(name: str) -> str | None:
    try:
        return (SYSCTL_ROOT / name.replace(".", "/")).read_text().strip()
    except OSError:
        return None


def write_sysctl(name: str, value: str) -> bool:
    """Best effort: /proc/sys is read-only in containers, the host must set it."""
    try:
        (SYSCTL_ROOT / name.replace(".", "/")).write_text(value)
    except OSError as e:
        log.debug("cannot write sysctl %s=%s: %s", name, value, e)
        return False
    return True
