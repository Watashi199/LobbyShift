"""SQLite persistence: configs, events, devices and runtime preferences.

One file replaces v1's scattered JSON files; writes are transactional.
The database holds private keys, so it is created with mode 0600.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
MAX_EVENTS = 500

_SCHEMA = """
CREATE TABLE IF NOT EXISTS configs (
    name         TEXT PRIMARY KEY,
    display_name TEXT,
    provider     TEXT NOT NULL DEFAULT 'custom',
    body         TEXT NOT NULL,
    country      TEXT,
    favorite     INTEGER NOT NULL DEFAULT 0,
    latency_ms   REAL,
    latency_at   TEXT,
    meta         TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    ts      TEXT NOT NULL,
    action  TEXT NOT NULL,
    config  TEXT,
    details TEXT
);
CREATE TABLE IF NOT EXISTS devices (
    ip   TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_CONFIG_FIELDS = {"display_name", "provider", "body", "country", "favorite",
                  "latency_ms", "latency_at", "meta"}


def now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(fd)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        # executescript() commits on its own, so it must run outside tx().
        with self._lock:
            self._db.executescript(_SCHEMA)
            self._db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def close(self) -> None:
        with self._lock:
            self._db.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                yield self._db
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            self._db.execute("COMMIT")

    def _query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._db.execute(sql, params).fetchall()

    # -- configs -----------------------------------------------------------

    @staticmethod
    def _config_row(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data["favorite"] = bool(data["favorite"])
        data["meta"] = json.loads(data["meta"] or "{}")
        return data

    def list_configs(self) -> list[dict[str, Any]]:
        rows = self._query("SELECT * FROM configs ORDER BY favorite DESC, lower(name)")
        return [self._config_row(r) for r in rows]

    def get_config(self, name: str) -> dict[str, Any] | None:
        rows = self._query("SELECT * FROM configs WHERE name = ?", (name,))
        return self._config_row(rows[0]) if rows else None

    def insert_config(self, name: str, body: str, *, provider: str, country: str | None,
                      meta: dict, display_name: str | None = None,
                      favorite: bool = False) -> None:
        ts = now()
        with self.tx() as db:
            db.execute(
                "INSERT INTO configs (name, display_name, provider, body, country, favorite,"
                " meta, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (name, display_name, provider, body, country, int(favorite),
                 json.dumps(meta), ts, ts),
            )

    def update_config(self, name: str, **fields: Any) -> bool:
        unknown = set(fields) - _CONFIG_FIELDS
        if unknown:
            raise ValueError(f"unknown config fields: {sorted(unknown)}")
        if not fields:
            return self.get_config(name) is not None
        if "meta" in fields:
            fields["meta"] = json.dumps(fields["meta"])
        if "favorite" in fields:
            fields["favorite"] = int(bool(fields["favorite"]))
        fields["updated_at"] = now()
        assignments = ", ".join(f"{k} = ?" for k in fields)  # keys checked against allowlist
        with self.tx() as db:
            cur = db.execute(
                f"UPDATE configs SET {assignments} WHERE name = ?",  # noqa: S608
                (*fields.values(), name),
            )
            return cur.rowcount > 0

    def delete_config(self, name: str) -> bool:
        with self.tx() as db:
            return db.execute("DELETE FROM configs WHERE name = ?", (name,)).rowcount > 0

    # -- events ------------------------------------------------------------

    def add_event(self, action: str, config: str | None = None, details: str | None = None) -> None:
        with self.tx() as db:
            db.execute(
                "INSERT INTO events (ts, action, config, details) VALUES (?, ?, ?, ?)",
                (now(), action, config, details),
            )
            db.execute(
                "DELETE FROM events WHERE id NOT IN"
                " (SELECT id FROM events ORDER BY id DESC LIMIT ?)",
                (MAX_EVENTS,),
            )

    def list_events(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._query("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    def clear_events(self) -> None:
        with self.tx() as db:
            db.execute("DELETE FROM events")

    # -- devices -----------------------------------------------------------

    def list_devices(self) -> list[dict[str, str]]:
        return [dict(r) for r in self._query("SELECT ip, name FROM devices ORDER BY ip")]

    def set_devices(self, devices: list[dict[str, str]]) -> None:
        with self.tx() as db:
            db.execute("DELETE FROM devices")
            db.executemany(
                "INSERT INTO devices (ip, name) VALUES (?, ?)",
                [(d["ip"], d.get("name", "")) for d in devices],
            )

    # -- key/value ---------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        rows = self._query("SELECT value FROM kv WHERE key = ?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

    def set(self, key: str, value: Any) -> None:
        with self.tx() as db:
            db.execute(
                "INSERT INTO kv (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value)),
            )

    def delete(self, key: str) -> None:
        with self.tx() as db:
            db.execute("DELETE FROM kv WHERE key = ?", (key,))
