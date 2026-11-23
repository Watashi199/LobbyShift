"""Static settings: YAML file, overridden by LOBBYSHIFT_* environment variables.

Runtime preferences the UI can change (autostart, kill switch, devices...)
live in the SQLite store, not here.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import field_validator
from pydantic.fields import FieldInfo
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

log = logging.getLogger(__name__)

DEFAULT_CONFIG_FILE = Path("/etc/lobbyshift/config.yaml")
DEFAULT_ROUTED = ["185.34.0.0/16"]
_IFNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,15}$")

# v1 config.yaml keys that were renamed.
_LEGACY_KEYS = {"interface": "lan_interface"}
# v1 keys that moved to the runtime store (migrated by lobbyshift.migrate).
_RUNTIME_KEYS = {"autostart", "autostart_config", "server_ip", "log_file"}


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError) as e:
        log.warning("Ignoring unreadable config file %s: %s", path, e)
        return {}
    if not isinstance(data, dict):
        log.warning("Ignoring config file %s: expected a mapping", path)
        return {}
    return data


class _YamlSource(PydanticBaseSettingsSource):
    def __init__(self, settings_cls: type[BaseSettings], path: Path):
        super().__init__(settings_cls)
        raw = _load_yaml(path)
        self.data = {_LEGACY_KEYS.get(k, k): v for k, v in raw.items() if k not in _RUNTIME_KEYS}

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        return self.data.get(field_name), field_name, False

    def __call__(self) -> dict[str, Any]:
        return {k: v for k, v in self.data.items() if k in self.settings_cls.model_fields}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOBBYSHIFT_", extra="ignore")

    # LAN side. Empty = auto-detect from the default route.
    lan_interface: str = ""
    lan_subnet: str = ""

    # Tunnel
    wg_interface: str = "lobbyshift"
    routing_table: int = 51820
    rule_priority: int = 5210
    routed_ranges: list[str] = DEFAULT_ROUTED.copy()

    # Web
    web_host: str = "0.0.0.0"  # noqa: S104 - a LAN gateway UI must listen on the LAN
    web_port: int = 8080
    admin_password: str = ""  # only used to seed the password on first start

    # Storage / misc
    data_dir: Path = Path("/var/lib/lobbyshift")
    legacy_dir: Path = Path("/etc/lobbyshift")
    log_level: str = "INFO"
    geoip_auto_update: bool = True

    @field_validator("lan_interface", "wg_interface")
    @classmethod
    def _ifname(cls, v: str) -> str:
        if v and not _IFNAME_RE.fullmatch(v):
            raise ValueError(f"invalid interface name: {v!r}")
        return v

    @field_validator("lan_subnet")
    @classmethod
    def _subnet(cls, v: str) -> str:
        return str(ipaddress.IPv4Network(v, strict=False)) if v else v

    @field_validator("routed_ranges", mode="before")
    @classmethod
    def _ranges(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = [item for item in re.split(r"[,\s]+", v) if item]
        nets = [str(ipaddress.IPv4Network(item, strict=False)) for item in v]
        if not nets:
            raise ValueError("routed_ranges must not be empty")
        return nets

    @field_validator("routing_table", "rule_priority")
    @classmethod
    def _positive(cls, v: int) -> int:
        if not 1 <= v < 2**31:
            raise ValueError("must be a positive 32-bit integer")
        return v

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        path = Path(os.environ.get("LOBBYSHIFT_CONFIG_FILE", DEFAULT_CONFIG_FILE))
        # Legacy v1 key `allowed_ips` maps to routed_ranges.
        source = _YamlSource(settings_cls, path)
        if "allowed_ips" in source.data and "routed_ranges" not in source.data:
            source.data["routed_ranges"] = source.data.pop("allowed_ips")
        return (init_settings, env_settings, source)
