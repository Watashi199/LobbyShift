"""Parse, validate and render WireGuard client configs.

Only an allowlist of keys survives parsing. Everything wg-quick would execute
(PreUp/PostUp/PreDown/PostDown) or that changes host networking (DNS, Table,
SaveConfig, FwMark) is dropped, so an uploaded config can never run commands
or alter the host beyond the tunnel LobbyShift builds itself.

These are pure functions: no I/O, fully unit-tested.
"""

from __future__ import annotations

import base64
import binascii
import ipaddress
import re
from dataclasses import dataclass, field, replace

HIDDEN = "[HIDDEN]"

_INTERFACE_KEYS = {"privatekey", "address", "listenport", "mtu", "dns"}
_PEER_KEYS = {"publickey", "presharedkey", "endpoint", "allowedips", "persistentkeepalive"}
_MULTI_VALUE_KEYS = {"address", "allowedips", "dns"}

_SECTION_RE = re.compile(r"\[(\w+)\]")
_LABEL = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?"
_HOSTNAME_RE = re.compile(rf"(?=.{{1,253}}$){_LABEL}(?:\.{_LABEL})*")


class ConfigError(ValueError):
    """Raised when a WireGuard config is malformed or unsupported."""


@dataclass(frozen=True)
class Endpoint:
    host: str
    port: int

    @property
    def is_ip(self) -> bool:
        try:
            ipaddress.ip_address(self.host)
        except ValueError:
            return False
        return True

    def __str__(self) -> str:
        return f"[{self.host}]:{self.port}" if ":" in self.host else f"{self.host}:{self.port}"


@dataclass(frozen=True)
class WgConfig:
    private_key: str
    addresses: tuple[str, ...]
    peer_public_key: str
    endpoint: Endpoint
    preshared_key: str | None = None
    persistent_keepalive: int | None = None
    listen_port: int | None = None
    mtu: int | None = None
    # Comment lines found in each section. Providers (e.g. Proton) put
    # metadata there: server name, feature flags.
    interface_comments: tuple[str, ...] = ()
    peer_comments: tuple[str, ...] = ()
    # Keys that were present but dropped (PostUp, DNS, ...), for user feedback.
    ignored_keys: tuple[str, ...] = field(default=(), compare=False)


def parse_endpoint(value: str) -> Endpoint:
    value = value.strip()
    match = re.fullmatch(r"\[([0-9A-Fa-f:.]+)\]:(\d{1,5})", value)
    if match:
        host, port = match.group(1), int(match.group(2))
        try:
            ipaddress.IPv6Address(host)
        except ValueError as e:
            raise ConfigError(f"Invalid IPv6 endpoint: {value!r}") from e
    else:
        match = re.fullmatch(r"([^\s:\[\]]+):(\d{1,5})", value)
        if not match:
            raise ConfigError(f"Invalid Endpoint (expected host:port): {value!r}")
        host, port = match.group(1), int(match.group(2))
        if not _is_ipv4(host) and not _HOSTNAME_RE.fullmatch(host):
            raise ConfigError(f"Invalid Endpoint host: {host!r}")
    if not 1 <= port <= 65535:
        raise ConfigError(f"Invalid Endpoint port: {port}")
    return Endpoint(host, port)


def _is_ipv4(value: str) -> bool:
    try:
        ipaddress.IPv4Address(value)
    except ValueError:
        return False
    return True


def _check_key(value: str, label: str) -> str:
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ConfigError(f"{label} is not valid base64") from e
    if len(raw) != 32:
        raise ConfigError(f"{label} must be a 32-byte WireGuard key")
    return value


def _int(value: str, label: str, lo: int, hi: int) -> int:
    try:
        number = int(value)
    except ValueError as e:
        raise ConfigError(f"{label} must be an integer") from e
    if not lo <= number <= hi:
        raise ConfigError(f"{label} must be between {lo} and {hi}")
    return number


def _split_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse(text: str, *, existing_private_key: str | None = None) -> WgConfig:
    """Parse a wg-quick style config.

    ``existing_private_key`` lets an edited config keep its key when the user
    saves the redacted text (``PrivateKey = [HIDDEN]``) shown by the UI.
    """
    section: str | None = None
    seen_interface = False
    interface: dict[str, str] = {}
    peers: list[dict[str, str]] = []
    iface_comments: list[str] = []
    peer_comments: list[list[str]] = []
    ignored: list[str] = []

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if line[0] in "#;":
            comment = line[1:].strip()
            if section == "interface":
                iface_comments.append(comment)
            elif section == "peer":
                peer_comments[-1].append(comment)
            continue

        header = _SECTION_RE.fullmatch(line)
        if header:
            name = header.group(1).lower()
            if name == "interface":
                if seen_interface:
                    raise ConfigError("Config has more than one [Interface] section")
                seen_interface = True
                section = "interface"
            elif name == "peer":
                peers.append({})
                peer_comments.append([])
                section = "peer"
            else:
                raise ConfigError(f"Unknown section [{header.group(1)}] on line {lineno}")
            continue

        if "=" not in line:
            raise ConfigError(f"Invalid line {lineno}: expected 'Key = Value'")
        if section is None:
            raise ConfigError(f"Line {lineno} is outside of any section")

        raw_key, _, value = line.partition("=")
        key = raw_key.strip().lower()
        # wg(8) treats '#' as the start of a comment anywhere on a line.
        value = value.split("#", 1)[0].strip()

        target = interface if section == "interface" else peers[-1]
        allowed = _INTERFACE_KEYS if section == "interface" else _PEER_KEYS
        if key not in allowed:
            ignored.append(raw_key.strip())
            continue
        if key in _MULTI_VALUE_KEYS and key in target:
            target[key] = f"{target[key]}, {value}"
        else:
            target[key] = value

    if not seen_interface:
        raise ConfigError("Missing [Interface] section")
    if not peers:
        raise ConfigError("Missing [Peer] section")
    if len(peers) > 1:
        raise ConfigError("Only single-peer configs are supported")
    peer = peers[0]

    private_key = interface.get("privatekey")
    if not private_key:
        raise ConfigError("Missing PrivateKey in [Interface]")
    if private_key == HIDDEN:
        if not existing_private_key:
            raise ConfigError("PrivateKey is hidden; paste the real key")
        private_key = existing_private_key
    _check_key(private_key, "PrivateKey")

    if "address" not in interface:
        raise ConfigError("Missing Address in [Interface]")
    addresses: list[str] = []
    for item in _split_list(interface["address"]):
        try:
            addresses.append(str(ipaddress.ip_interface(item)))
        except ValueError as e:
            raise ConfigError(f"Invalid Address: {item!r}") from e
    if not any(ipaddress.ip_interface(a).version == 4 for a in addresses):
        raise ConfigError("At least one IPv4 Address is required")

    public_key = peer.get("publickey")
    if not public_key:
        raise ConfigError("Missing PublicKey in [Peer]")
    _check_key(public_key, "PublicKey")

    if "endpoint" not in peer:
        raise ConfigError("Missing Endpoint in [Peer]")
    endpoint = parse_endpoint(peer["endpoint"])

    preshared = peer.get("presharedkey") or None
    if preshared:
        _check_key(preshared, "PresharedKey")

    # AllowedIPs from the provider is always replaced by the routed ranges,
    # and DNS is never applied: both are parsed only to accept the config.
    if "dns" in interface:
        ignored.append("DNS")

    return WgConfig(
        private_key=private_key,
        addresses=tuple(addresses),
        peer_public_key=public_key,
        endpoint=endpoint,
        preshared_key=preshared,
        persistent_keepalive=(
            _int(peer["persistentkeepalive"], "PersistentKeepalive", 0, 65535)
            if peer.get("persistentkeepalive") and peer["persistentkeepalive"] != "off"
            else None
        ),
        listen_port=(
            _int(interface["listenport"], "ListenPort", 1, 65535)
            if interface.get("listenport")
            else None
        ),
        mtu=_int(interface["mtu"], "MTU", 1280, 9000) if interface.get("mtu") else None,
        interface_comments=tuple(iface_comments),
        peer_comments=tuple(peer_comments[0]),
        ignored_keys=tuple(dict.fromkeys(ignored)),
    )


def render_setconf(cfg: WgConfig, allowed_ips: list[str]) -> str:
    """Render the config for ``wg setconf`` (crypto only, no wg-quick keys)."""
    lines = ["[Interface]", f"PrivateKey = {cfg.private_key}"]
    if cfg.listen_port:
        lines.append(f"ListenPort = {cfg.listen_port}")
    lines += ["", "[Peer]", f"PublicKey = {cfg.peer_public_key}"]
    if cfg.preshared_key:
        lines.append(f"PresharedKey = {cfg.preshared_key}")
    lines.append(f"Endpoint = {cfg.endpoint}")
    lines.append(f"AllowedIPs = {', '.join(allowed_ips)}")
    if cfg.persistent_keepalive:
        lines.append(f"PersistentKeepalive = {cfg.persistent_keepalive}")
    return "\n".join(lines) + "\n"


def render(cfg: WgConfig, *, hide_private_key: bool = False) -> str:
    """Render the canonical stored form (wg-quick syntax, safe keys only)."""
    lines = ["[Interface]"]
    lines += [f"# {c}" for c in cfg.interface_comments]
    lines.append(f"PrivateKey = {HIDDEN if hide_private_key else cfg.private_key}")
    lines.append(f"Address = {', '.join(cfg.addresses)}")
    if cfg.listen_port:
        lines.append(f"ListenPort = {cfg.listen_port}")
    if cfg.mtu:
        lines.append(f"MTU = {cfg.mtu}")
    lines += ["", "[Peer]"]
    lines += [f"# {c}" for c in cfg.peer_comments]
    lines.append(f"PublicKey = {cfg.peer_public_key}")
    if cfg.preshared_key:
        lines.append(f"PresharedKey = {HIDDEN if hide_private_key else cfg.preshared_key}")
    lines.append(f"Endpoint = {cfg.endpoint}")
    if cfg.persistent_keepalive:
        lines.append(f"PersistentKeepalive = {cfg.persistent_keepalive}")
    return "\n".join(lines) + "\n"


def with_hidden_preshared(cfg: WgConfig, existing: WgConfig | None) -> WgConfig:
    """Restore a PresharedKey that was redacted in the edit UI."""
    if existing and cfg.preshared_key == HIDDEN:
        return replace(cfg, preshared_key=existing.preshared_key)
    return cfg


def sanitize_name(name: str) -> str:
    """Turn an uploaded filename into a safe config identifier."""
    stem = re.sub(r"\.conf$", "", name.strip(), flags=re.IGNORECASE)
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_")
    if not stem:
        raise ConfigError("Config name is empty")
    return stem[:64]
