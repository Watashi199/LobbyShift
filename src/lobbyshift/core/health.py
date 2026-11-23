"""Latency probes for VPN endpoints.

WireGuard never answers unauthenticated packets, so we measure the server
itself: ICMP via the system ``ping`` (needs CAP_NET_RAW or ping_group_range),
falling back to a TCP connect on 443, which most VPN servers expose.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import socket
import time

from ..runner import Runner

_RTT_RE = re.compile(r"= [\d.]+/([\d.]+)/")
STALE_HANDSHAKE_SECONDS = 180


async def resolve(host: str) -> str | None:
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None, type=socket.SOCK_DGRAM)
    except OSError:
        return None
    return infos[0][4][0] if infos else None


async def icmp_rtt(runner: Runner, ip: str, count: int = 3) -> float | None:
    res = await runner.run(
        "ping", "-n", "-q", "-c", str(count), "-i", "0.2", "-W", "1", ip, check=False
    )
    match = _RTT_RE.search(res.stdout)
    return float(match.group(1)) if res.ok and match else None


async def tcp_rtt(ip: str, port: int = 443, tries: int = 3, timeout: float = 1.5) -> float | None:
    best: float | None = None
    for _ in range(tries):
        start = time.perf_counter()
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout)
        except (OSError, TimeoutError):
            continue
        elapsed = (time.perf_counter() - start) * 1000
        writer.close()
        with contextlib.suppress(OSError):
            await writer.wait_closed()
        best = elapsed if best is None else min(best, elapsed)
    return best


async def measure(runner: Runner, host: str) -> float | None:
    """Round-trip time in milliseconds, or None if unreachable."""
    ip = await resolve(host)
    if not ip:
        return None
    rtt = await icmp_rtt(runner, ip)
    if rtt is None:
        rtt = await tcp_rtt(ip)
    return round(rtt, 1) if rtt is not None else None
