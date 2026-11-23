"""VPN provider integrations: extract provider metadata from imported configs."""

from __future__ import annotations

from ..core.wgconfig import WgConfig
from . import proton


def detect(cfg: WgConfig) -> tuple[str, dict]:
    """Return (provider id, metadata) for a parsed config."""
    if proton.matches(cfg):
        return proton.PROVIDER, proton.metadata(cfg)
    return "custom", {}
