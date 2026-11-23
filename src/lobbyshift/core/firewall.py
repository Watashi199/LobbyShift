"""nftables ruleset for the gateway, applied atomically with ``nft -f -``.

Everything lives in a single ``inet lobbyshift`` table, so cleanup is one
command and applying a new ruleset never leaves a half-configured state.
"""

from __future__ import annotations

import ipaddress
import logging
import re
from dataclasses import dataclass

from ..runner import Runner

log = logging.getLogger(__name__)

TABLE = "lobbyshift"
_IFNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,15}$")
_DOCKER_COMMENT = "lobbyshift"


@dataclass(frozen=True)
class FirewallSpec:
    lan_interface: str
    lan_subnet: str
    wg_interface: str
    clients: tuple[str, ...]  # sources routed through the VPN
    routed: tuple[str, ...]  # destination ranges (CoD matchmaking)
    kill_switch: bool = False


def _ifname(name: str) -> str:
    if not _IFNAME_RE.fullmatch(name):
        raise ValueError(f"invalid interface name: {name!r}")
    return name


def _nets(values: tuple[str, ...]) -> list[str]:
    return [str(ipaddress.IPv4Network(v, strict=False)) for v in values]


def _set(name: str, elements: list[str]) -> list[str]:
    lines = [f"  set {name} {{", "    type ipv4_addr", "    flags interval", "    auto-merge"]
    if elements:
        lines.append(f"    elements = {{ {', '.join(elements)} }}")
    lines.append("  }")
    return lines


def render_ruleset(spec: FirewallSpec) -> str:
    lan_if = _ifname(spec.lan_interface)
    wg_if = _ifname(spec.wg_interface)
    lan = _nets((spec.lan_subnet,))
    clients = _nets(spec.clients)
    routed = _nets(spec.routed)

    lines = [
        # Declare-then-delete makes the replacement atomic and idempotent.
        f"table inet {TABLE}",
        f"delete table inet {TABLE}",
        f"table inet {TABLE} {{",
        *_set("lan", lan),
        *_set("clients", clients),
        *_set("routed", routed),
        "",
        "  chain forward {",
        "    type filter hook forward priority filter; policy accept;",
        # Avoid PMTU black holes inside the tunnel.
        f'    oifname "{wg_if}" tcp flags syn tcp option maxseg size set rt mtu',
    ]
    if spec.kill_switch:
        lines.append(
            f'    ip saddr @clients ip daddr @routed oifname != "{wg_if}" counter drop'
        )
    lines += [
        "  }",
        "",
        "  chain postrouting {",
        "    type nat hook postrouting priority srcnat; policy accept;",
        f'    oifname "{wg_if}" masquerade',
        # Gateway mode: consoles use this host as their router.
        f'    oifname "{lan_if}" ip saddr @lan ip daddr != @lan masquerade',
        "  }",
        "}",
    ]
    return "\n".join(lines) + "\n"


class Firewall:
    def __init__(self, runner: Runner):
        self.runner = runner

    async def apply(self, spec: FirewallSpec) -> None:
        await self.runner.run("nft", "-f", "-", input=render_ruleset(spec))
        await self._docker_forward(spec, add=True)

    async def remove(self, spec: FirewallSpec | None = None) -> None:
        await self.runner.run("nft", "delete", "table", "inet", TABLE, check=False)
        if spec:
            await self._docker_forward(spec, add=False)

    async def kill_switch_drops(self) -> int | None:
        """Packets dropped by the kill switch since the ruleset was applied."""
        res = await self.runner.run("nft", "list", "chain", "inet", TABLE, "forward", check=False)
        match = re.search(r"counter packets (\d+)", res.stdout)
        return int(match.group(1)) if match else None

    async def _docker_forward(self, spec: FirewallSpec, *, add: bool) -> None:
        """Docker sets the iptables FORWARD policy to DROP, which would cut the
        consoles off. An accept in our nft table cannot override a drop in
        Docker's table, so we whitelist the LAN in DOCKER-USER instead."""
        # Docker may drive either iptables backend; use the one that has its chain.
        for binary in ("iptables", "iptables-legacy"):
            if (await self.runner.run(binary, "-w", "-n", "-L", "DOCKER-USER", check=False)).ok:
                break
        else:
            return
        lan_if = _ifname(spec.lan_interface)
        lan = _nets((spec.lan_subnet,))[0]
        comment = ["-m", "comment", "--comment", _DOCKER_COMMENT]
        rules = [
            ["-i", lan_if, "-s", lan, *comment, "-j", "ACCEPT"],
            ["-o", lan_if, "-d", lan, "-m", "conntrack", "--ctstate", "RELATED,ESTABLISHED",
             *comment, "-j", "ACCEPT"],
        ]
        for rule in rules:
            exists = (await self.runner.run(binary, "-w", "-C", "DOCKER-USER", *rule, check=False)).ok
            if add and not exists:
                await self.runner.run(binary, "-w", "-I", "DOCKER-USER", *rule)
                log.info("Docker detected: allowed LAN forwarding in DOCKER-USER (%s)", binary)
            elif not add and exists:
                await self.runner.run(binary, "-w", "-D", "DOCKER-USER", *rule, check=False)
