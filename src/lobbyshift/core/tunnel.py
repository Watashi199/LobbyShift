"""WireGuard tunnel lifecycle without wg-quick.

    ip link add <if> type wireguard
    wg setconf <if> <tmpfile>           # crypto only, cannot run commands
    ip address add <addr> dev <if>
    ip route replace <routed> dev <if> table <T>
    ip rule add from <client> lookup <T> pref <P>

Only the routed ranges live in table T, so for any other destination the
lookup falls through to the main table: traffic goes out directly. Host
traffic is untouched because the rules match on the clients' source address.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import tempfile
import time
from dataclasses import dataclass

from ..network import write_sysctl
from ..runner import CommandError, Runner
from .wgconfig import WgConfig, render_setconf

log = logging.getLogger(__name__)

DEFAULT_MTU = 1420
_MAX_RULE_FLUSH = 512


@dataclass(frozen=True)
class TunnelStats:
    endpoint: str | None
    latest_handshake: int | None  # unix timestamp, None = never
    rx_bytes: int
    tx_bytes: int

    @property
    def handshake_age(self) -> float | None:
        return None if self.latest_handshake is None else max(0.0, time.time() - self.latest_handshake)


class Tunnel:
    def __init__(self, runner: Runner, interface: str, table: int, rule_priority: int):
        self.runner = runner
        self.interface = interface
        self.table = str(table)
        self.pref = str(rule_priority)

    async def up(self, cfg: WgConfig, routed: list[str], clients: list[str]) -> None:
        await self.down()
        ifc = self.interface
        await self.runner.run("ip", "link", "add", "dev", ifc, "type", "wireguard")
        try:
            await self._setconf(render_setconf(cfg, routed))
            for addr in cfg.addresses:
                v4 = ipaddress.ip_interface(addr).version == 4
                # IPv6 may be disabled on the host; only IPv4 is required.
                await self.runner.run("ip", "address", "add", addr, "dev", ifc, check=v4)
            await self.runner.run(
                "ip", "link", "set", "dev", ifc, "mtu", str(cfg.mtu or DEFAULT_MTU), "up"
            )
            for net in routed:
                await self.runner.run("ip", "route", "replace", net, "dev", ifc, "table", self.table)
            await self.set_clients(clients)
            # Replies come back on the tunnel; strict rp_filter would drop them.
            write_sysctl(f"net.ipv4.conf.{ifc}.rp_filter", "2")
        except CommandError:
            await self.down()
            raise

    async def _setconf(self, text: str) -> None:
        # wg must open() its config path. /dev/stdin cannot be used: under uvloop
        # the child's stdin is a socket, and opening /proc/self/fd/0 on a socket
        # fails with ENXIO. A private temp file (mode 0600) is removed right away.
        fd, path = tempfile.mkstemp(prefix="lobbyshift-", suffix=".conf")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(text)
            await self.runner.run("wg", "setconf", self.interface, path)
        finally:
            os.unlink(path)

    async def set_clients(self, clients: list[str]) -> None:
        await self._flush_rules()
        for src in clients:
            await self.runner.run(
                "ip", "rule", "add", "from", src, "lookup", self.table, "pref", self.pref
            )

    async def down(self) -> None:
        await self._flush_rules()
        await self.runner.run("ip", "route", "flush", "table", self.table, check=False)
        await self.runner.run("ip", "link", "del", "dev", self.interface, check=False)

    async def is_up(self) -> bool:
        res = await self.runner.run("ip", "link", "show", "dev", self.interface, check=False)
        return res.ok

    async def stats(self) -> TunnelStats | None:
        res = await self.runner.run("wg", "show", self.interface, "dump", check=False)
        if not res.ok:
            return None
        return parse_dump(res.stdout)

    async def _flush_rules(self) -> None:
        for _ in range(_MAX_RULE_FLUSH):
            res = await self.runner.run("ip", "rule", "del", "pref", self.pref, check=False)
            if not res.ok:
                return
        log.warning("Stopped flushing ip rules after %d deletions", _MAX_RULE_FLUSH)


def parse_dump(text: str) -> TunnelStats | None:
    """Parse ``wg show <if> dump`` (line 1 = interface, line 2 = our peer)."""
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    fields = lines[1].split("\t")
    if len(fields) < 8:
        return None
    endpoint = None if fields[2] == "(none)" else fields[2]
    handshake = int(fields[4]) if fields[4].isdigit() and fields[4] != "0" else None
    return TunnelStats(
        endpoint=endpoint,
        latest_handshake=handshake,
        rx_bytes=int(fields[5]) if fields[5].isdigit() else 0,
        tx_bytes=int(fields[6]) if fields[6].isdigit() else 0,
    )
