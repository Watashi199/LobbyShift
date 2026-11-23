"""End-to-end API tests against the FastAPI app with a fake network stack."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lobbyshift.app import create_app
from lobbyshift.settings import Settings

from .conftest import proton_conf
from .fakes import FakeRunner

PASSWORD = "correct-horse"


@pytest.fixture
def runner() -> FakeRunner:
    return FakeRunner()


def make_settings(tmp_path: Path, **kw) -> Settings:
    return Settings(data_dir=tmp_path / "data", legacy_dir=tmp_path / "legacy",
                    admin_password=PASSWORD, geoip_auto_update=False, **kw)


@pytest.fixture
def client(tmp_path, runner):
    app = create_app(make_settings(tmp_path), runner, background=False)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def authed(client):
    r = client.post("/api/auth/login", json={"password": PASSWORD})
    assert r.status_code == 200
    return client


def upload(client, name="MX-12.conf", text=None):
    text = text or proton_conf()
    return client.post("/api/configs", files=[("files", (name, text.encode(), "text/plain"))])


# ------------------------------------------------------------------- auth

def test_api_requires_auth(client):
    for method, path in [("get", "/api/status"), ("get", "/api/configs"),
                         ("post", "/api/tunnel/up"), ("post", "/api/configs")]:
        assert getattr(client, method)(path).status_code == 401
    assert client.get("/api/health").status_code == 200


def test_wrong_password_and_throttle(client):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"password": "nope"}).status_code == 401
    assert client.post("/api/auth/login", json={"password": PASSWORD}).status_code == 429


def test_session_cookie_flags(client):
    r = client.post("/api/auth/login", json={"password": PASSWORD})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie


def test_cross_origin_writes_are_refused(authed):
    upload(authed)
    r = authed.post("/api/tunnel/connect/MX-12", headers={"Origin": "http://evil.example"})
    assert r.status_code == 403


def test_bearer_token_for_cli(client, tmp_path):
    token = (tmp_path / "data" / "cli-token").read_text()
    r = client.get("/api/status", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_change_password_rotates_sessions(authed):
    r = authed.put("/api/auth/password", json={"current": PASSWORD, "new": "another-pass"})
    assert r.status_code == 200
    assert authed.get("/api/status").status_code == 200  # fresh cookie was issued
    authed.cookies.clear()
    assert authed.post("/api/auth/login", json={"password": PASSWORD}).status_code == 401


def test_generated_initial_password(tmp_path, runner):
    settings = Settings(data_dir=tmp_path / "d", legacy_dir=tmp_path / "l",
                        geoip_auto_update=False)
    with TestClient(create_app(settings, runner, background=False)) as c:
        password = (tmp_path / "d" / "initial-password").read_text().strip()
        assert c.post("/api/auth/login", json={"password": password}).status_code == 200


def test_security_headers(client):
    r = client.get("/api/health")
    assert "script-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"


# ---------------------------------------------------------------- configs

def test_upload_proton_config(authed):
    r = upload(authed, text=proton_conf(extra_interface="PostUp = rm -rf /"))
    assert r.status_code == 200
    cfg = r.json()["imported"][0]
    assert cfg["name"] == "MX-12"
    assert cfg["provider"] == "proton"
    assert cfg["country"]["code"] == "MX"
    assert "PostUp" in cfg["meta"]["ignored_keys"]


def test_upload_rejects_garbage(authed):
    r = upload(authed, name="x.conf", text="hello")
    assert r.status_code == 400
    assert r.json()["detail"]["errors"][0]["file"] == "x.conf"
    assert upload(authed, name="x.txt").status_code == 400


def test_upload_zip(authed):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("proton/JP-3.conf", proton_conf(server="JP#3"))
        z.writestr("proton/broken.conf", "nope")
        z.writestr("readme.txt", "ignored")
    r = authed.post("/api/configs", files=[("files", ("all.zip", buf.getvalue(), "application/zip"))])
    body = r.json()
    assert [c["name"] for c in body["imported"]] == ["JP-3"]
    assert body["errors"][0]["file"] == "broken.conf"


def test_duplicate_names_get_suffix(authed):
    upload(authed)
    assert upload(authed).json()["imported"][0]["name"] == "MX-12-2"


def test_edit_keeps_hidden_private_key(authed, runner):
    upload(authed)
    text = authed.get("/api/configs/MX-12").json()["text"]
    assert "PrivateKey = [HIDDEN]" in text
    r = authed.put("/api/configs/MX-12/text",
                   json={"text": text.replace("203.0.113.7", "203.0.113.9")})
    assert r.status_code == 200
    assert r.json()["endpoint"] == "203.0.113.9:51820"
    # The tunnel still gets a real key.
    authed.post("/api/tunnel/connect/MX-12")
    setconf = runner.inputs[("wg", "setconf", "lobbyshift")]
    assert "[HIDDEN]" not in setconf


def test_patch_and_delete(authed):
    upload(authed)
    r = authed.patch("/api/configs/MX-12", json={"display_name": "<b>Mexico</b>", "favorite": True})
    assert r.json()["display_name"] == "<b>Mexico</b>"  # stored raw, escaped by the UI
    assert r.json()["favorite"] is True
    assert authed.delete("/api/configs/MX-12").status_code == 200
    assert authed.get("/api/configs/MX-12").status_code == 404


# ----------------------------------------------------------------- tunnel

def test_connect_status_disconnect(authed, runner):
    upload(authed)
    r = authed.post("/api/tunnel/connect/MX-12")
    assert r.status_code == 200
    status = authed.get("/api/status").json()
    assert status["active"] is True
    assert status["config"]["name"] == "MX-12"
    assert status["tunnel"]["rx_bytes"] == 2048
    assert status["clients"] == ["192.168.1.0/24"]

    assert authed.post("/api/tunnel/down").status_code == 200
    assert authed.get("/api/status").json()["active"] is False
    actions = [e["action"] for e in authed.get("/api/events").json()["events"]]
    assert actions[:2] == ["disconnected", "connected"]


def test_up_uses_last_config(authed):
    upload(authed, name="A.conf")
    upload(authed, name="B.conf")
    authed.post("/api/tunnel/connect/B")
    authed.post("/api/tunnel/down")
    assert authed.post("/api/tunnel/up").json()["config"]["name"] == "B"


def test_connect_failure_is_reported(authed, runner):
    upload(authed)
    runner.fail.add("wg setconf")
    r = authed.post("/api/tunnel/connect/MX-12")
    assert r.status_code == 400
    assert "tunnel" in r.json()["detail"]
    assert authed.get("/api/status").json()["active"] is False


def test_devices_restrict_clients(authed, runner):
    upload(authed)
    authed.post("/api/tunnel/connect/MX-12")
    r = authed.put("/api/settings/devices", json={"devices": [{"ip": "192.168.1.20", "name": "PS5"}]})
    assert r.status_code == 200
    assert [rule[1] for rule in runner.rules] == ["192.168.1.20/32"]
    bad = authed.put("/api/settings/devices", json={"devices": [{"ip": "10.0.0.1"}]})
    assert bad.status_code == 400


def test_kill_switch_reapplies_firewall(authed, runner):
    authed.put("/api/settings/prefs", json={"kill_switch": True})
    ruleset = [v for k, v in runner.inputs.items() if k[:2] == ("nft", "-f")][-1]
    assert "counter drop" in ruleset


def test_autostart_requires_existing_config(authed):
    r = authed.put("/api/settings/prefs", json={"autostart": True, "autostart_config": "nope"})
    assert r.status_code == 400


def test_latency(authed):
    upload(authed)
    configs = authed.post("/api/latency", json={}).json()["configs"]
    assert configs[0]["latency_ms"] == 23.4


# ------------------------------------------------------------ lifecycle

def test_restart_adopts_running_tunnel(tmp_path, runner):
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings, runner, background=False)) as c:
        c.post("/api/auth/login", json={"password": PASSWORD})
        upload(c)
        c.post("/api/tunnel/connect/MX-12")
    assert "lobbyshift" in runner.links  # left up across restarts
    with TestClient(create_app(settings, runner, background=False)) as c:
        c.post("/api/auth/login", json={"password": PASSWORD})
        assert c.get("/api/status").json()["config"]["name"] == "MX-12"


def test_autostart(tmp_path, runner):
    settings = make_settings(tmp_path)
    with TestClient(create_app(settings, runner, background=False)) as c:
        c.post("/api/auth/login", json={"password": PASSWORD})
        upload(c)
        c.put("/api/settings/prefs", json={"autostart": True, "autostart_config": "MX-12"})
    runner.links.clear()  # reboot
    with TestClient(create_app(settings, runner, background=False)) as c:
        c.post("/api/auth/login", json={"password": PASSWORD})
        assert c.get("/api/status").json()["active"] is True


async def test_watchdog_reconnects_stale_tunnel(tmp_path, runner):
    from lobbyshift.core.geoip import GeoIP
    from lobbyshift.service import LobbyShift
    from lobbyshift.store import Store

    settings = make_settings(tmp_path)
    store = Store(tmp_path / "s.db")
    svc = LobbyShift(settings, store, runner, GeoIP(tmp_path / "none.mmdb"))
    await svc.start(background=False)
    await svc.import_config("MX-12.conf", proton_conf())
    await svc.connect("MX-12")

    runner.handshake_age = 600
    await svc.check_health()
    assert svc.health["state"] in ("stale", "checking")
    assert store.list_events(1)[0]["action"] == "reconnected"

    runner.handshake_age = 5
    await svc.check_health()
    assert svc.health["state"] == "ok"


def test_legacy_migration(tmp_path, runner):
    legacy = tmp_path / "legacy"
    (legacy / "configs").mkdir(parents=True)
    (legacy / "configs" / "mexico.conf").write_text(proton_conf())
    (legacy / "configs" / "japan.conf").write_text(proton_conf(server="JP#3"))
    (legacy / "favorites.json").write_text(json.dumps(["japan"]))
    (legacy / "config_names.json").write_text(json.dumps({"mexico": "Mexico City"}))
    (legacy / "connection_logs.json").write_text(json.dumps(
        [{"timestamp": "2025-01-01T00:00:00", "action": "connected", "config": "mexico"}]))
    (legacy / "config.yaml").write_text("autostart: true\nautostart_config: japan\n")

    with TestClient(create_app(make_settings(tmp_path), runner, background=False)) as c:
        c.post("/api/auth/login", json={"password": PASSWORD})
        configs = {cfg["name"]: cfg for cfg in c.get("/api/configs").json()["configs"]}
        assert configs["mexico"]["display_name"] == "Mexico City"
        assert configs["japan"]["favorite"] is True
        assert c.get("/api/settings").json()["prefs"]["autostart_config"] == "japan"
        assert c.get("/api/status").json()["config"]["name"] == "japan"  # autostarted


def test_settings_yaml_legacy_keys(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    path.write_text("interface: enp1s0\nallowed_ips:\n  - 185.34.0.0/16\n  - 10.10.0.0/16\n"
                    "web_port: 9000\nautostart: true\n")
    monkeypatch.setenv("LOBBYSHIFT_CONFIG_FILE", str(path))
    monkeypatch.setenv("LOBBYSHIFT_WEB_PORT", "9100")
    s = Settings()
    assert s.lan_interface == "enp1s0"
    assert s.routed_ranges == ["185.34.0.0/16", "10.10.0.0/16"]
    assert s.web_port == 9100  # env wins over YAML
