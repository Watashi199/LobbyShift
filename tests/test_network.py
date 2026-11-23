import pytest

from lobbyshift.core.firewall import Firewall, FirewallSpec, render_ruleset
from lobbyshift.core.tunnel import Tunnel, parse_dump
from lobbyshift.core.wgconfig import parse
from lobbyshift.network import detect_lan
from lobbyshift.runner import CommandError

from .conftest import proton_conf
from .fakes import FakeRunner

SPEC = FirewallSpec(
    lan_interface="eth0",
    lan_subnet="192.168.1.0/24",
    wg_interface="lobbyshift",
    clients=("192.168.1.20/32",),
    routed=("185.34.0.0/16",),
)


def test_ruleset_is_atomic_and_scoped():
    rules = render_ruleset(SPEC)
    assert rules.startswith("table inet lobbyshift\ndelete table inet lobbyshift\n")
    assert "elements = { 185.34.0.0/16 }" in rules
    assert "elements = { 192.168.1.20/32 }" in rules
    assert 'oifname "lobbyshift" masquerade' in rules
    assert 'oifname "eth0" ip saddr @lan ip daddr != @lan masquerade' in rules
    assert "drop" not in rules


def test_kill_switch_rule():
    from dataclasses import replace

    rules = render_ruleset(replace(SPEC, kill_switch=True))
    assert 'ip saddr @clients ip daddr @routed oifname != "lobbyshift" counter drop' in rules


@pytest.mark.parametrize("field, value", [
    ("lan_interface", 'eth0"; flush ruleset; "'),
    ("wg_interface", "a" * 20),
    ("lan_subnet", "not-a-subnet"),
])
def test_ruleset_rejects_injection(field, value):
    from dataclasses import replace

    with pytest.raises(ValueError):
        render_ruleset(replace(SPEC, **{field: value}))


async def test_firewall_whitelists_lan_when_docker_present():
    runner = FakeRunner(docker=True)
    fw = Firewall(runner)
    await fw.apply(SPEC)
    await fw.apply(SPEC)  # idempotent
    assert len(runner.docker_rules) == 2
    await fw.remove(SPEC)
    assert runner.docker_rules == []


async def test_firewall_skips_docker_rules_without_docker():
    runner = FakeRunner()
    await Firewall(runner).apply(SPEC)
    assert runner.commands("iptables -w -I") == []
    assert runner.commands("nft -f -")


async def test_tunnel_up_uses_policy_routing_not_wg_quick():
    runner = FakeRunner()
    tunnel = Tunnel(runner, "lobbyshift", 51820, 5210)
    cfg = parse(proton_conf())
    await tunnel.up(cfg, ["185.34.0.0/16"], ["192.168.1.0/24"])

    flat = [" ".join(c) for c in runner.calls]
    assert not any(c.startswith("wg-quick") for c in flat)
    assert "ip link add dev lobbyshift type wireguard" in flat
    assert "ip route replace 185.34.0.0/16 dev lobbyshift table 51820" in flat
    assert "ip rule add from 192.168.1.0/24 lookup 51820 pref 5210" in flat
    setconf = runner.inputs[("wg", "setconf", "lobbyshift")]
    assert "AllowedIPs = 185.34.0.0/16" in setconf
    assert await tunnel.is_up()

    await tunnel.down()
    assert not await tunnel.is_up()
    assert runner.rules == []


async def test_tunnel_up_rolls_back_on_failure():
    runner = FakeRunner()
    runner.fail.add("wg setconf")
    tunnel = Tunnel(runner, "lobbyshift", 51820, 5210)
    with pytest.raises(CommandError):
        await tunnel.up(parse(proton_conf()), ["185.34.0.0/16"], ["192.168.1.0/24"])
    assert not await tunnel.is_up()


async def test_set_clients_replaces_rules():
    runner = FakeRunner()
    tunnel = Tunnel(runner, "lobbyshift", 51820, 5210)
    await tunnel.up(parse(proton_conf()), ["185.34.0.0/16"], ["192.168.1.0/24"])
    await tunnel.set_clients(["192.168.1.20/32", "192.168.1.21/32"])
    assert [r[1] for r in runner.rules] == ["192.168.1.20/32", "192.168.1.21/32"]


def test_parse_dump():
    stats = parse_dump("priv\tpub\t0\toff\n"
                       "peer\t(none)\t1.2.3.4:51820\t185.34.0.0/16\t1700000000\t100\t200\t25\n")
    assert stats.endpoint == "1.2.3.4:51820"
    assert stats.latest_handshake == 1700000000
    assert (stats.rx_bytes, stats.tx_bytes) == (100, 200)


def test_parse_dump_never_handshaked():
    stats = parse_dump("priv\tpub\t0\toff\npeer\t(none)\t(none)\t185.34.0.0/16\t0\t0\t0\toff\n")
    assert stats.latest_handshake is None
    assert stats.handshake_age is None
    assert stats.endpoint is None


async def test_detect_lan():
    lan = await detect_lan(FakeRunner(lan_dev="enp3s0", lan_ip="10.0.0.5", prefix=16))
    assert (lan.interface, lan.subnet, lan.address) == ("enp3s0", "10.0.0.0/16", "10.0.0.5")
