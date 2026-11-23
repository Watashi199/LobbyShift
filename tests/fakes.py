"""In-memory stand-in for ip/wg/nft/ping, shared by tests and the dev server."""

from __future__ import annotations

import json
import time

from lobbyshift.runner import CommandError, Result


class FakeRunner:
    def __init__(self, *, lan_dev: str = "eth0", lan_ip: str = "192.168.1.50", prefix: int = 24,
                 docker: bool = False):
        self.calls: list[tuple[str, ...]] = []
        self.inputs: dict[tuple[str, ...], str] = {}
        self.links: set[str] = set()
        self.rules: list[tuple[str, ...]] = []
        self.lan_dev, self.lan_ip, self.prefix = lan_dev, lan_ip, prefix
        self.docker = docker
        self.docker_rules: list[tuple[str, ...]] = []
        self.handshake_age: int | None = 10
        self.fail: set[str] = set()  # argv[0:2] joined, e.g. "wg setconf"

    def commands(self, prefix: str) -> list[tuple[str, ...]]:
        return [c for c in self.calls if " ".join(c).startswith(prefix)]

    async def run(self, *argv: str, input: str | None = None, check: bool = True) -> Result:
        self.calls.append(argv)
        if input is not None:
            self.inputs[argv] = input
        result = self._dispatch(argv)
        if check and not result.ok:
            raise CommandError(argv, result)
        return result

    def _dispatch(self, argv: tuple[str, ...]) -> Result:
        ok, err = Result(0, "", ""), Result(1, "", "error")
        if " ".join(argv[:2]) in self.fail:
            return Result(1, "", f"simulated failure: {' '.join(argv)}")
        match argv:
            case ("ip", "-j", "-4", "route", "show", "default"):
                return Result(0, json.dumps([{"dst": "default", "dev": self.lan_dev}]), "")
            case ("ip", "-j", "-4", "addr", "show", "dev", dev):
                if dev != self.lan_dev:
                    return Result(0, "[]", "")
                info = [{"family": "inet", "local": self.lan_ip, "prefixlen": self.prefix}]
                return Result(0, json.dumps([{"ifname": dev, "addr_info": info}]), "")
            case ("ip", "link", "add", "dev", dev, *_):
                if dev in self.links:
                    return err
                self.links.add(dev)
                return ok
            case ("ip", "link", "del", "dev", dev):
                if dev not in self.links:
                    return err
                self.links.discard(dev)
                return ok
            case ("ip", "link", "show", "dev", dev):
                return ok if dev in self.links else err
            case ("ip", "rule", "add", *rest):
                self.rules.append(tuple(rest))
                return ok
            case ("ip", "rule", "del", "pref", _):
                if not self.rules:
                    return err
                self.rules.pop(0)
                return ok
            case ("wg", "setconf", dev, path):
                with open(path) as f:  # the real file must exist while wg runs
                    self.inputs[("wg", "setconf", dev)] = f.read()
                return ok
            case ("wg", "show", dev, "dump"):
                if dev not in self.links:
                    return err
                now = int(time.time())
                hs = 0 if self.handshake_age is None else now - self.handshake_age
                return Result(0, "priv\tpub\t0\toff\n"
                                 f"peer\t(none)\t203.0.113.7:51820\t185.34.0.0/16\t{hs}\t2048\t1024\t25\n", "")
            case ("ping", *_):
                return Result(0, "rtt min/avg/max/mdev = 20.1/23.4/25.0/1.2 ms\n", "")
            case ("iptables", "-w", "-n", "-L", "DOCKER-USER"):
                return ok if self.docker else Result(1, "", "No chain")
            case ("iptables", "-w", "-C", "DOCKER-USER", *rule):
                return ok if tuple(rule) in self.docker_rules else err
            case ("iptables", "-w", "-I", "DOCKER-USER", *rule):
                self.docker_rules.append(tuple(rule))
                return ok
            case ("iptables", "-w", "-D", "DOCKER-USER", *rule):
                self.docker_rules.remove(tuple(rule))
                return ok
            case ("iptables-legacy", *_):
                return Result(1, "", "No chain")
            case _:
                return ok
