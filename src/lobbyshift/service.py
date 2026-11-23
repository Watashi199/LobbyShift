"""LobbyShift orchestrator: ties tunnel, firewall, store, GeoIP and health.

The kernel is the source of truth for the tunnel: on start we adopt an
interface that is already up (service restart, upgrade, crash) instead of
pretending nothing is running. Stopping the service leaves the tunnel and
gateway rules in place so consoles are not cut off during an upgrade; use
``lobbyshift down`` (or the UI) to disconnect.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import ipaddress
import json
import logging
import time
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from . import providers
from .core.firewall import Firewall, FirewallSpec
from .core.geoip import UNKNOWN, Country, GeoIP, flag
from .core.health import STALE_HANDSHAKE_SECONDS, measure
from .core.tunnel import Tunnel
from .core.wgconfig import (
    ConfigError,
    WgConfig,
    parse,
    render,
    sanitize_name,
    with_hidden_preshared,
)
from .network import LanInfo, NetworkError, detect_lan, read_sysctl, write_sysctl
from .runner import CommandError, Runner
from .settings import Settings
from .store import Store

log = logging.getLogger(__name__)

DEFAULT_KEEPALIVE = 25
WATCHDOG_INTERVAL = 30
RECONNECT_COOLDOWN = 120
MAX_CONFIG_BYTES = 64 * 1024
MAX_ARCHIVE_FILES = 200

DEFAULT_PREFS = {
    "autostart": False,
    "autostart_config": "",
    "kill_switch": False,
    "auto_reconnect": True,
}


class ServiceError(Exception):
    status = 400


class NotFoundError(ServiceError):
    status = 404


class UnavailableError(ServiceError):
    status = 503


class LobbyShift:
    def __init__(self, settings: Settings, store: Store, runner: Runner, geoip: GeoIP):
        self.settings = settings
        self.store = store
        self.runner = runner
        self.geoip = geoip
        self.tunnel = Tunnel(
            runner, settings.wg_interface, settings.routing_table, settings.rule_priority
        )
        self.firewall = Firewall(runner)
        self.lan: LanInfo | None = None
        self.active: str | None = None
        self.connected_at: float | None = None
        self.health: dict[str, Any] = {"state": "down"}
        self.problems: list[str] = []
        self._lock = asyncio.Lock()
        self._tasks: list[asyncio.Task] = []
        self._last_reconnect = 0.0

    # ------------------------------------------------------------------ life

    async def start(self, *, background: bool = True) -> None:
        try:
            self.lan = await detect_lan(
                self.runner, self.settings.lan_interface, self.settings.lan_subnet
            )
            log.info("LAN: %s %s (gateway address %s)",
                     self.lan.interface, self.lan.subnet, self.lan.address)
        except NetworkError as e:
            self._problem(str(e))

        if read_sysctl("net.ipv4.ip_forward") != "1" and not write_sysctl("net.ipv4.ip_forward", "1"):
            self._problem("IP forwarding is disabled: set net.ipv4.ip_forward=1 on the host")

        await self.migrate_legacy()

        if self.lan:
            try:
                await self.apply_network()
            except CommandError as e:
                self._problem(f"Firewall setup failed: {e}")

        if await self.tunnel.is_up():
            name = self.store.get("active_config")
            if name and self.store.get_config(name):
                self.active = name
                self.connected_at = time.time()
                self.health = {"state": "checking"}
                log.info("Adopted running tunnel for %s", name)
            else:
                await self.tunnel.down()
        else:
            prefs = self.prefs()
            if prefs["autostart"] and prefs["autostart_config"]:
                try:
                    await self.connect(prefs["autostart_config"])
                except (ServiceError, CommandError) as e:
                    self._problem(f"Autostart failed: {e}")

        if background:
            self._tasks = [
                asyncio.create_task(self._watchdog(), name="watchdog"),
                asyncio.create_task(self._geoip_updater(), name="geoip"),
            ]

    async def shutdown(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks = []

    def _problem(self, message: str) -> None:
        log.error(message)
        if message not in self.problems:
            self.problems.append(message)

    # ----------------------------------------------------------------- prefs

    def prefs(self) -> dict[str, Any]:
        stored = self.store.get("prefs", {})
        return {**DEFAULT_PREFS, **{k: v for k, v in stored.items() if k in DEFAULT_PREFS}}

    async def update_prefs(self, changes: dict[str, Any]) -> dict[str, Any]:
        prefs = self.prefs()
        unknown = set(changes) - set(DEFAULT_PREFS)
        if unknown:
            raise ServiceError(f"Unknown settings: {', '.join(sorted(unknown))}")
        prefs.update(changes)
        # autostart_config is kept while autostart is off, so the choice is remembered.
        if prefs["autostart"] and not self.store.get_config(prefs["autostart_config"] or ""):
            raise ServiceError("Autostart needs an existing config")
        old = self.prefs()
        self.store.set("prefs", prefs)
        if prefs["kill_switch"] != old["kill_switch"] and self.lan:
            await self.apply_network()
        return prefs

    def devices(self) -> list[dict[str, str]]:
        return self.store.list_devices()

    async def set_devices(self, devices: list[dict[str, str]]) -> list[dict[str, str]]:
        clean: dict[str, dict[str, str]] = {}
        for device in devices:
            try:
                ip = str(ipaddress.IPv4Address(str(device.get("ip", "")).strip()))
            except ValueError as e:
                raise ServiceError(f"Invalid device IP: {device.get('ip')!r}") from e
            if self.lan and ipaddress.IPv4Address(ip) not in ipaddress.IPv4Network(self.lan.subnet):
                raise ServiceError(f"{ip} is not in the LAN subnet {self.lan.subnet}")
            clean[ip] = {"ip": ip, "name": str(device.get("name", "")).strip()[:64]}
        self.store.set_devices(list(clean.values()))
        if self.lan:
            await self.apply_network()
        return self.devices()

    # --------------------------------------------------------------- network

    def clients(self) -> list[str]:
        ips = [d["ip"] for d in self.store.list_devices()]
        if ips:
            return [f"{ip}/32" for ip in ips]
        return [self.lan.subnet] if self.lan else []

    def _require_lan(self) -> LanInfo:
        if not self.lan:
            raise UnavailableError("LAN interface not detected; see /api/system/doctor")
        return self.lan

    async def apply_network(self) -> None:
        lan = self._require_lan()
        spec = FirewallSpec(
            lan_interface=lan.interface,
            lan_subnet=lan.subnet,
            wg_interface=self.settings.wg_interface,
            clients=tuple(self.clients()),
            routed=tuple(self.settings.routed_ranges),
            kill_switch=self.prefs()["kill_switch"],
        )
        await self.firewall.apply(spec)
        if self.active and await self.tunnel.is_up():
            await self.tunnel.set_clients(self.clients())

    # --------------------------------------------------------------- configs

    def _public(self, row: dict[str, Any]) -> dict[str, Any]:
        try:
            cfg = parse(row["body"])
            endpoint = str(cfg.endpoint)
        except ConfigError:
            endpoint = None
        code = row["country"] or UNKNOWN.code
        return {
            "name": row["name"],
            "display_name": row["display_name"],
            "provider": row["provider"],
            "country": {"code": code, "flag": flag(code)},
            "endpoint": endpoint,
            "favorite": row["favorite"],
            "active": row["name"] == self.active,
            "latency_ms": row["latency_ms"],
            "latency_at": row["latency_at"],
            "meta": row["meta"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def list_configs(self) -> list[dict[str, Any]]:
        return [self._public(r) for r in self.store.list_configs()]

    def _row(self, name: str) -> dict[str, Any]:
        row = self.store.get_config(name)
        if not row:
            raise NotFoundError(f"Config not found: {name}")
        return row

    def get_config(self, name: str) -> dict[str, Any]:
        return self._public(self._row(name))

    def get_config_text(self, name: str) -> str:
        return render(parse(self._row(name)["body"]), hide_private_key=True)

    async def _describe(self, cfg: WgConfig) -> tuple[str, str | None, dict]:
        provider, meta = providers.detect(cfg)
        meta["ignored_keys"] = list(cfg.ignored_keys)
        country = meta.get("country")
        if not country:
            found: Country = await asyncio.to_thread(self.geoip.lookup_host, cfg.endpoint.host)
            country = None if found is UNKNOWN else found.code
        return provider, country, meta

    def _unique_name(self, base: str) -> str:
        name, n = base, 2
        while self.store.get_config(name):
            name = f"{base[:60]}-{n}"
            n += 1
        return name

    async def import_config(self, filename: str, data: bytes | str,
                            *, display_name: str | None = None,
                            favorite: bool = False) -> dict[str, Any]:
        if isinstance(data, bytes):
            if len(data) > MAX_CONFIG_BYTES:
                raise ServiceError("Config file is too large")
            try:
                data = data.decode("utf-8-sig")
            except UnicodeDecodeError as e:
                raise ServiceError("Config file is not UTF-8 text") from e
        try:
            name = self._unique_name(sanitize_name(filename))
            cfg = parse(data)
        except ConfigError as e:
            raise ServiceError(str(e)) from e
        provider, country, meta = await self._describe(cfg)
        self.store.insert_config(name, render(cfg), provider=provider, country=country,
                                 meta=meta, display_name=display_name, favorite=favorite)
        self.store.add_event("imported", name, f"{provider} · {cfg.endpoint}")
        return self.get_config(name)

    async def import_upload(self, filename: str, data: bytes) -> dict[str, Any]:
        """Import a single .conf or a .zip of configs."""
        if filename.lower().endswith(".zip"):
            return await self._import_zip(data)
        if not filename.lower().endswith(".conf"):
            raise ServiceError("Upload a .conf file or a .zip of .conf files")
        return {"imported": [await self.import_config(filename, data)], "errors": []}

    async def _import_zip(self, data: bytes) -> dict[str, Any]:
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as e:
            raise ServiceError("Invalid zip archive") from e
        members = [m for m in archive.infolist()
                   if not m.is_dir() and m.filename.lower().endswith(".conf")]
        if not members:
            raise ServiceError("The archive contains no .conf file")
        if len(members) > MAX_ARCHIVE_FILES:
            raise ServiceError(f"Too many files (max {MAX_ARCHIVE_FILES})")
        imported, errors = [], []
        for member in members:
            filename = Path(member.filename).name
            if member.file_size > MAX_CONFIG_BYTES:
                errors.append({"file": filename, "error": "File is too large"})
                continue
            try:
                imported.append(await self.import_config(filename, archive.read(member)))
            except ServiceError as e:
                errors.append({"file": filename, "error": str(e)})
        return {"imported": imported, "errors": errors}

    async def update_config_text(self, name: str, text: str) -> dict[str, Any]:
        row = self._row(name)
        existing = parse(row["body"])
        try:
            cfg = parse(text, existing_private_key=existing.private_key)
        except ConfigError as e:
            raise ServiceError(str(e)) from e
        cfg = with_hidden_preshared(cfg, existing)
        provider, country, meta = await self._describe(cfg)
        self.store.update_config(name, body=render(cfg), provider=provider,
                                 country=country, meta=meta, latency_ms=None, latency_at=None)
        self.store.add_event("edited", name)
        if self.active == name:
            await self.connect(name)
        return self.get_config(name)

    def update_config_fields(self, name: str, *, display_name: str | None = None,
                             favorite: bool | None = None) -> dict[str, Any]:
        self._row(name)
        fields: dict[str, Any] = {}
        if display_name is not None:
            fields["display_name"] = display_name.strip()[:64] or None
        if favorite is not None:
            fields["favorite"] = favorite
        self.store.update_config(name, **fields)
        return self.get_config(name)

    async def delete_config(self, name: str) -> None:
        self._row(name)
        if self.active == name:
            await self.disconnect()
        self.store.delete_config(name)
        prefs = self.prefs()
        if prefs["autostart_config"] == name:
            self.store.set("prefs", {**prefs, "autostart": False, "autostart_config": ""})
        if self.store.get("last_config") == name:
            self.store.delete("last_config")
        self.store.add_event("deleted", name)

    # ---------------------------------------------------------------- tunnel

    async def connect(self, name: str, *, event: str = "connected") -> dict[str, Any]:
        row = self._row(name)
        self._require_lan()
        cfg = parse(row["body"])
        cfg = replace(cfg, persistent_keepalive=cfg.persistent_keepalive or DEFAULT_KEEPALIVE)
        async with self._lock:
            try:
                await self.tunnel.up(cfg, list(self.settings.routed_ranges), self.clients())
            except CommandError as e:
                self.active = None
                self.store.delete("active_config")
                self.health = {"state": "down", "error": str(e)}
                self.store.add_event("error", name, str(e))
                raise ServiceError(f"Could not bring the tunnel up: {e}") from e
            self.active = name
            self.connected_at = time.time()
            self.health = {"state": "checking"}
            self.store.set("active_config", name)
            self.store.set("last_config", name)
        self.store.add_event(event, name, f"{row['country'] or '??'} · {cfg.endpoint}")
        return self.get_config(name)

    async def disconnect(self) -> None:
        async with self._lock:
            name = self.active
            await self.tunnel.down()
            self.active = None
            self.connected_at = None
            self.health = {"state": "down"}
            self.store.delete("active_config")
        if name:
            self.store.add_event("disconnected", name)

    async def up(self) -> dict[str, Any]:
        if self.active:
            return self.get_config(self.active)
        prefs = self.prefs()
        for candidate in (self.store.get("last_config"), prefs["autostart_config"]):
            if candidate and self.store.get_config(candidate):
                return await self.connect(candidate)
        configs = self.store.list_configs()
        if not configs:
            raise ServiceError("No config available: import one first")
        return await self.connect(configs[0]["name"])

    async def status(self) -> dict[str, Any]:
        stats = await self.tunnel.stats() if self.active else None
        return {
            "active": self.active is not None,
            "config": self.get_config(self.active) if self.active else None,
            "connected_at": self.connected_at,
            "tunnel": {
                "interface": self.settings.wg_interface,
                "endpoint": stats.endpoint if stats else None,
                "handshake_age": round(stats.handshake_age) if stats and stats.handshake_age is not None else None,
                "rx_bytes": stats.rx_bytes if stats else 0,
                "tx_bytes": stats.tx_bytes if stats else 0,
            },
            "health": self.health,
            "lan": self.lan.__dict__ if self.lan else None,
            "clients": self.clients(),
            "routed_ranges": list(self.settings.routed_ranges),
            "prefs": self.prefs(),
            "problems": self.problems,
        }

    # --------------------------------------------------------------- latency

    async def measure_latency(self, names: list[str] | None = None) -> list[dict[str, Any]]:
        rows = [r for r in self.store.list_configs() if names is None or r["name"] in names]
        semaphore = asyncio.Semaphore(8)

        async def probe(row: dict[str, Any]) -> None:
            try:
                host = parse(row["body"]).endpoint.host
            except ConfigError:
                return
            async with semaphore:
                rtt = await measure(self.runner, host)
            self.store.update_config(row["name"], latency_ms=rtt,
                                     latency_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

        await asyncio.gather(*(probe(r) for r in rows))
        return self.list_configs()

    # -------------------------------------------------------- background jobs

    async def check_health(self) -> None:
        if not self.active:
            return
        stats = await self.tunnel.stats()
        now = time.time()
        since_connect = now - (self.connected_at or now)
        if stats is None:
            self.health = {"state": "down", "error": "Tunnel interface disappeared"}
        elif stats.handshake_age is None:
            state = "checking" if since_connect < 30 else "stale"
            self.health = {"state": state, "handshake_age": None}
        elif stats.handshake_age > STALE_HANDSHAKE_SECONDS:
            self.health = {"state": "stale", "handshake_age": round(stats.handshake_age)}
        else:
            self.health = {"state": "ok", "handshake_age": round(stats.handshake_age)}

        if (self.health["state"] in ("stale", "down")
                and self.prefs()["auto_reconnect"]
                and now - self._last_reconnect > RECONNECT_COOLDOWN):
            self._last_reconnect = now
            log.warning("Tunnel %s is %s, reconnecting", self.active, self.health["state"])
            with contextlib.suppress(ServiceError):
                await self.connect(self.active, event="reconnected")

    async def _watchdog(self) -> None:
        while True:
            await asyncio.sleep(WATCHDOG_INTERVAL)
            try:
                await self.check_health()
            except Exception:
                log.exception("Watchdog iteration failed")

    async def update_geoip(self) -> bool:
        updated = await asyncio.to_thread(self.geoip.update)
        if updated:
            await self._backfill_countries()
        return updated

    async def _backfill_countries(self) -> None:
        for row in self.store.list_configs():
            if row["country"]:
                continue
            try:
                host = parse(row["body"]).endpoint.host
            except ConfigError:
                continue
            found = await asyncio.to_thread(self.geoip.lookup_host, host)
            if found is not UNKNOWN:
                self.store.update_config(row["name"], country=found.code)

    async def _geoip_updater(self) -> None:
        while True:
            if self.settings.geoip_auto_update and self.geoip.needs_update():
                try:
                    await self.update_geoip()
                except Exception:
                    log.exception("GeoIP update failed")
            await asyncio.sleep(86400)

    # ---------------------------------------------------------------- doctor

    async def doctor(self) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []

        def add(name: str, ok: bool, detail: str = "") -> None:
            checks.append({"check": name, "ok": ok, "detail": detail})

        add("LAN detected", self.lan is not None,
            f"{self.lan.interface} {self.lan.subnet}" if self.lan else "set lan_interface")
        add("IP forwarding", read_sysctl("net.ipv4.ip_forward") == "1",
            "sysctl net.ipv4.ip_forward=1")
        for tool, argv in (("ip", ("ip", "-V")), ("wg", ("wg", "--version")),
                           ("nft", ("nft", "--version"))):
            res = await self.runner.run(*argv, check=False)
            add(f"`{tool}` available", res.ok, (res.stdout or res.stderr).strip()[:80])
        wg_module = Path("/sys/module/wireguard").exists() or await self.tunnel.is_up()
        add("WireGuard kernel module", wg_module, "modprobe wireguard")
        res = await self.runner.run("nft", "list", "table", "inet", "lobbyshift", check=False)
        add("Gateway firewall loaded", res.ok, "nft table inet lobbyshift")
        add("GeoIP database", self.geoip.available, "DB-IP Lite, refreshed monthly")
        for problem in self.problems:
            add("Startup", False, problem)
        return checks

    # ------------------------------------------------------------- migration

    async def migrate_legacy(self) -> None:
        """Import v1 data from /etc/lobbyshift once (configs, names, favorites, logs)."""
        if self.store.get("legacy_migrated"):
            return
        root = self.settings.legacy_dir
        conf_dir = root / "configs"
        if not conf_dir.is_dir():
            self.store.set("legacy_migrated", True)
            return

        def load(name: str, default: Any) -> Any:
            try:
                return json.loads((root / name).read_text())
            except (OSError, ValueError):
                return default

        favorites = set(load("favorites.json", []))
        names = load("config_names.json", {})
        count = 0
        for path in sorted(conf_dir.glob("*.conf")):
            if self.store.get_config(path.stem):
                continue
            try:
                await self.import_config(path.name, path.read_bytes(),
                                         display_name=names.get(path.stem),
                                         favorite=path.stem in favorites)
                count += 1
            except (OSError, ServiceError) as e:
                self._problem(f"Could not migrate {path.name}: {e}")

        for entry in reversed(load("connection_logs.json", [])):
            if isinstance(entry, dict) and entry.get("action"):
                self.store.add_event(entry["action"], entry.get("config"), entry.get("details"))

        try:
            import yaml

            old = yaml.safe_load((root / "config.yaml").read_text()) or {}
        except (OSError, ValueError):
            old = {}
        if old.get("autostart") and self.store.get_config(old.get("autostart_config", "")):
            self.store.set("prefs", {**self.prefs(), "autostart": True,
                                     "autostart_config": old["autostart_config"]})

        self.store.set("legacy_migrated", True)
        if count:
            self.store.add_event("migrated", None, f"{count} config(s) imported from v1")
            log.info("Migrated %d v1 config(s) from %s", count, conf_dir)
