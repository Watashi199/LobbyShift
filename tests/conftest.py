from __future__ import annotations

import base64
import os
from collections.abc import Callable

import pytest


def make_key() -> str:
    return base64.b64encode(os.urandom(32)).decode()


def proton_conf(server: str = "MX#12", endpoint: str = "203.0.113.7:51820",
                moderate_nat: str = "on", extra_interface: str = "") -> str:
    return f"""[Interface]
# Key for test
# NetShield = 0
# Moderate NAT = {moderate_nat}
# NAT-PMP (Port Forwarding) = off
# VPN Accelerator = on
PrivateKey = {make_key()}
Address = 10.2.0.2/32
DNS = 10.2.0.1
{extra_interface}

[Peer]
# {server}
PublicKey = {make_key()}
AllowedIPs = 0.0.0.0/0
Endpoint = {endpoint}
"""


@pytest.fixture
def conf() -> Callable[..., str]:
    return proton_conf


@pytest.fixture(autouse=True)
def fake_sysctl(tmp_path, monkeypatch):
    """Never touch the real /proc/sys, even when tests run as root on Linux."""
    import lobbyshift.network

    root = tmp_path / "proc-sys"
    (root / "net" / "ipv4").mkdir(parents=True)
    (root / "net" / "ipv4" / "ip_forward").write_text("1\n")
    monkeypatch.setattr(lobbyshift.network, "SYSCTL_ROOT", root)
    return root
