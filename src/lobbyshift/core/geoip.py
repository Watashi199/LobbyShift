"""Offline GeoIP using the free DB-IP "Country Lite" database (CC BY 4.0).

No per-lookup network call, no rate limits, no IPs sent to third parties.
The database is refreshed monthly in a background thread.
"""

from __future__ import annotations

import datetime as dt
import gzip
import ipaddress
import logging
import os
import shutil
import socket
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import maxminddb

log = logging.getLogger(__name__)

DBIP_URL = "https://download.db-ip.com/free/dbip-country-lite-{month}.mmdb.gz"
MAX_AGE_DAYS = 35
USER_AGENT = "LobbyShift-GeoIP-Updater"


@dataclass(frozen=True)
class Country:
    code: str
    name: str | None = None

    def as_dict(self) -> dict:
        return {"code": self.code, "name": self.name, "flag": flag(self.code)}


UNKNOWN = Country("??", None)


def flag(code: str) -> str:
    """ISO 3166 alpha-2 code -> flag emoji (regional indicator symbols)."""
    code = {"UK": "GB"}.get(code.upper(), code.upper())
    if len(code) != 2 or not code.isalpha() or not code.isascii():
        return "\N{GLOBE WITH MERIDIANS}"
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code)


class GeoIP:
    def __init__(self, path: Path):
        self.path = path
        self._reader: maxminddb.Reader | None = None
        self._lock = threading.Lock()
        self._open()

    @property
    def available(self) -> bool:
        return self._reader is not None

    def _open(self) -> None:
        if not self.path.is_file():
            return
        try:
            reader = maxminddb.open_database(str(self.path))
        except (OSError, maxminddb.InvalidDatabaseError) as e:
            log.warning("GeoIP database unreadable (%s): %s", self.path, e)
            return
        with self._lock:
            old, self._reader = self._reader, reader
        if old:
            old.close()

    def lookup(self, ip: str) -> Country:
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            return UNKNOWN
        with self._lock:
            reader = self._reader
            record = reader.get(ip) if reader else None
        if not isinstance(record, dict):
            return UNKNOWN
        country = record.get("country") or {}
        code = country.get("iso_code")
        if not code:
            return UNKNOWN
        return Country(code, (country.get("names") or {}).get("en"))

    def lookup_host(self, host: str) -> Country:
        """Blocking (DNS). Call from a worker thread."""
        try:
            ipaddress.ip_address(host)
            ip = host
        except ValueError:
            try:
                ip = socket.getaddrinfo(host, None, type=socket.SOCK_DGRAM)[0][4][0]
            except OSError:
                return UNKNOWN
        return self.lookup(ip)

    def needs_update(self) -> bool:
        if not self.path.is_file():
            return True
        age = time.time() - self.path.stat().st_mtime
        return age > MAX_AGE_DAYS * 86400

    def update(self) -> bool:
        """Blocking download of the current (or previous) month's database."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        today = dt.date.today()
        previous = (today.replace(day=1) - dt.timedelta(days=1))
        for month in (today.strftime("%Y-%m"), previous.strftime("%Y-%m")):
            url = DBIP_URL.format(month=month)
            tmp = self.path.with_suffix(".tmp")
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
                with (
                    urllib.request.urlopen(req, timeout=60) as resp,  # noqa: S310
                    open(tmp, "wb") as out,
                    gzip.GzipFile(fileobj=resp) as gz,
                ):
                    shutil.copyfileobj(gz, out)
                maxminddb.open_database(str(tmp)).close()  # validate before swapping
            except urllib.error.HTTPError as e:
                tmp.unlink(missing_ok=True)
                if e.code == 404:
                    continue
                log.warning("GeoIP download failed: %s", e)
                return False
            except (OSError, maxminddb.InvalidDatabaseError) as e:
                tmp.unlink(missing_ok=True)
                log.warning("GeoIP download failed: %s", e)
                return False
            os.replace(tmp, self.path)
            self._open()
            log.info("GeoIP database updated (%s)", month)
            return True
        return False
