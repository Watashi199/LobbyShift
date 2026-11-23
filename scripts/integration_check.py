"""Real-kernel integration check, run INSIDE the Docker image (see CI).

    docker run -d --name ls --cap-drop ALL --cap-add NET_ADMIN --cap-add NET_RAW \
        -e LOBBYSHIFT_ADMIN_PASSWORD=integration-test lobbyshift:ci
    docker exec -i ls python - < scripts/integration_check.py

The container has its own network namespace, so nothing touches the host.
Exercises the real ip/wg/nft binaries: tunnel creation without wg-quick,
policy routing, nftables, kill switch, teardown, and that PostUp never runs.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid

API = "http://127.0.0.1:8080/api"
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'ok' if ok else 'FAIL'}] {name}{': ' + detail if detail and not ok else ''}")
    if not ok:
        failures.append(name)


def sh(cmd: str) -> str:
    return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip()  # noqa: S602


def call(method: str, path: str, body: bytes | None = None, ctype: str = "application/json"):
    req = urllib.request.Request(f"{API}{path}", method=method, data=body,  # noqa: S310
                                 headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def key() -> str:
    return base64.b64encode(os.urandom(32)).decode()


# Wait for the server to come up.
for _ in range(30):
    try:
        urllib.request.urlopen(f"{API}/health", timeout=2)  # noqa: S310
        break
    except OSError:
        time.sleep(1)
else:
    sys.exit("server did not start")

with open("/var/lib/lobbyshift/cli-token") as f:
    TOKEN = f.read().strip()

conf = f"""[Interface]
# Moderate NAT = on
PrivateKey = {key()}
Address = 10.2.0.2/32
DNS = 10.2.0.1
PostUp = touch /tmp/pwned

[Peer]
# MX#12
PublicKey = {key()}
AllowedIPs = 0.0.0.0/0
Endpoint = 203.0.113.7:51820
"""
boundary = uuid.uuid4().hex
body = (f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="mx-12.conf"\r\n'
        f"Content-Type: text/plain\r\n\r\n{conf}\r\n--{boundary}--\r\n").encode()

status, res = call("POST", "/configs", body, f"multipart/form-data; boundary={boundary}")
check("upload", status == 200, str(res))
check("proton detected", res.get("imported", [{}])[0].get("country", {}).get("code") == "MX", str(res))

status, res = call("POST", "/tunnel/connect/mx-12", b"{}")
check("connect", status == 200, str(res))

check("wireguard link up", "wireguard" in sh("ip -d link show lobbyshift"))
wg = sh("wg show lobbyshift")
check("allowed ips restricted", "allowed ips: 185.34.0.0/16" in wg, wg)
check("keepalive set", "persistent keepalive: every 25 seconds" in wg, wg)
check("policy rule", "lookup 51820" in sh("ip rule show"))
lan = json.loads(sh("ip -j -4 addr show dev eth0"))[0]["addr_info"][0]
client = lan["local"].rsplit(".", 1)[0] + ".99"
via_tunnel = sh(f"ip route get 185.34.1.1 from {client} iif eth0")
direct = sh(f"ip route get 1.1.1.1 from {client} iif eth0")
check("matchmaking via tunnel", "dev lobbyshift" in via_tunnel, via_tunnel)
check("other traffic direct", "dev eth0" in direct, direct)
check("nft table loaded", "masquerade" in sh("nft list table inet lobbyshift"))
check("PostUp not executed", not os.path.exists("/tmp/pwned"))  # noqa: S108 - the file a PostUp would create

status, _ = call("PUT", "/settings/prefs", json.dumps({"kill_switch": True}).encode())
check("kill switch rule", status == 200 and "drop" in sh("nft list chain inet lobbyshift forward"))

status, _ = call("POST", "/tunnel/down", b"{}")
check("disconnect", status == 200)
check("link removed", not sh("ip link show lobbyshift 2>/dev/null"))
check("rules removed", "51820" not in sh("ip rule show"))

print(f"\n{len(failures)} failure(s)")
sys.exit(1 if failures else 0)
