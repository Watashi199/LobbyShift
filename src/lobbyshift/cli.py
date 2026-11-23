"""`lobbyshift` command: run the server or drive it from a shell.

    lobbyshift serve                 run the web app (systemd / Docker)
    lobbyshift status | list | up | down | latency | doctor
    lobbyshift connect <name>
    lobbyshift passwd [--generate]   reset the admin password (local, no server needed)
"""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from . import __version__
from .settings import Settings


def _api(settings: Settings, method: str, path: str) -> Any:
    token_file = settings.data_dir / "cli-token"
    try:
        token = token_file.read_text().strip()
    except OSError:
        sys.exit(f"Cannot read {token_file} (run with sudo, or inside the container)")
    req = urllib.request.Request(
        f"http://127.0.0.1:{settings.web_port}/api{path}",
        method=method,
        data=b"{}" if method != "GET" else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            return json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read()).get("detail", e.reason)
        except ValueError:
            detail = e.reason
        sys.exit(f"Error {e.code}: {detail}")
    except urllib.error.URLError as e:
        sys.exit(f"LobbyShift is not reachable on port {settings.web_port}: {e.reason}")


def _print_configs(configs: list[dict]) -> None:
    for c in configs:
        mark = "*" if c["active"] else ("+" if c["favorite"] else " ")
        latency = f"{c['latency_ms']:.0f} ms" if c.get("latency_ms") is not None else "-"
        label = c["display_name"] or c["name"]
        print(f"{mark} {c['name']:<24} {c['country']['code']:<3} {latency:>8}  {label}")


def _serve(settings: Settings) -> None:
    import uvicorn

    from .app import create_app

    logging.basicConfig(level=settings.log_level.upper(),
                        format="%(levelname)s %(name)s: %(message)s")
    uvicorn.run(create_app(settings), host=settings.web_host, port=settings.web_port,
                log_level=settings.log_level.lower(), proxy_headers=False)


def _restore_ownership(data_dir: Path) -> None:
    """When run with sudo, hand created files (SQLite WAL, token) back to the service user."""
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        return
    owner = data_dir.stat()
    for path in data_dir.iterdir():
        os.chown(path, owner.st_uid, owner.st_gid)


def _passwd(settings: Settings, generate: bool) -> None:
    from .auth import Auth
    from .store import Store

    store = Store(settings.data_dir / "state.db")
    auth = Auth(store, settings.data_dir / "cli-token")
    auth.ensure_initialized()
    if generate:
        password = secrets.token_urlsafe(12)
    else:
        password = getpass.getpass("New admin password: ")
        if password != getpass.getpass("Repeat: "):
            sys.exit("Passwords do not match")
    try:
        auth.set_password(password)
    except ValueError as e:
        sys.exit(str(e))
    finally:
        store.close()
        _restore_ownership(settings.data_dir)
    (settings.data_dir / "initial-password").unlink(missing_ok=True)
    print(f"Admin password set{': ' + password if generate else ''}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="lobbyshift", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("serve")
    for name in ("status", "list", "up", "down", "latency", "doctor"):
        sub.add_parser(name)
    connect = sub.add_parser("connect", aliases=["switch"])
    connect.add_argument("name")
    passwd = sub.add_parser("passwd")
    passwd.add_argument("--generate", action="store_true")
    args = parser.parse_args(argv)
    settings = Settings()

    match args.cmd:
        case "serve":
            _serve(settings)
        case "passwd":
            _passwd(settings, args.generate)
        case "status":
            s = _api(settings, "GET", "/status")
            if s["active"]:
                c = s["config"]
                print(f"Connected: {c['display_name'] or c['name']} ({c['country']['code']}, {c['endpoint']})")
                print(f"Health:    {s['health']['state']}  handshake {s['tunnel']['handshake_age']}s ago")
                print(f"Traffic:   rx {s['tunnel']['rx_bytes']} B / tx {s['tunnel']['tx_bytes']} B")
            else:
                print("Disconnected")
            for problem in s["problems"]:
                print(f"! {problem}")
        case "list":
            _print_configs(_api(settings, "GET", "/configs")["configs"])
        case "up":
            c = _api(settings, "POST", "/tunnel/up")["config"]
            print(f"Connected to {c['name']}")
        case "down":
            _api(settings, "POST", "/tunnel/down")
            print("Disconnected")
        case "connect" | "switch":
            c = _api(settings, "POST", f"/tunnel/connect/{urllib.request.quote(args.name)}")["config"]
            print(f"Connected to {c['name']}")
        case "latency":
            _print_configs(_api(settings, "POST", "/latency")["configs"])
        case "doctor":
            report = _api(settings, "GET", "/system/doctor")
            for check in report["checks"]:
                print(f"[{'ok' if check['ok'] else '!!'}] {check['check']}: {check['detail']}")
            sys.exit(0 if report["ok"] else 1)
        case _:
            parser.print_help()


if __name__ == "__main__":
    main()
