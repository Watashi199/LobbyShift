import pytest

from lobbyshift.core.wgconfig import (
    HIDDEN,
    ConfigError,
    parse,
    parse_endpoint,
    render,
    render_setconf,
    sanitize_name,
)

from .conftest import make_key, proton_conf


def test_parse_proton_config():
    cfg = parse(proton_conf())
    assert cfg.addresses == ("10.2.0.2/32",)
    assert str(cfg.endpoint) == "203.0.113.7:51820"
    assert "MX#12" in cfg.peer_comments
    assert "Moderate NAT = on" in cfg.interface_comments


@pytest.mark.parametrize("key", ["PostUp", "PreUp", "PostDown", "PreDown", "SaveConfig", "Table",
                                 "FwMark"])
def test_command_and_routing_keys_are_dropped(key):
    cfg = parse(proton_conf(extra_interface=f"{key} = touch /tmp/pwned"))
    assert key in cfg.ignored_keys
    text = render(cfg) + render_setconf(cfg, ["185.34.0.0/16"])
    assert "pwned" not in text
    assert key not in text


def test_dns_is_never_applied():
    cfg = parse(proton_conf())
    assert "DNS" in cfg.ignored_keys
    assert "DNS" not in render(cfg)


def test_setconf_replaces_allowed_ips_and_has_no_wg_quick_keys():
    cfg = parse(proton_conf())
    out = render_setconf(cfg, ["185.34.0.0/16", "10.9.0.0/16"])
    assert "AllowedIPs = 185.34.0.0/16, 10.9.0.0/16" in out
    assert "0.0.0.0/0" not in out
    for forbidden in ("Address", "DNS", "MTU"):
        assert forbidden not in out


def test_hidden_private_key_is_restored_on_edit():
    original = parse(proton_conf())
    redacted = render(original, hide_private_key=True)
    assert original.private_key not in redacted
    assert HIDDEN in redacted
    edited = parse(redacted, existing_private_key=original.private_key)
    assert edited.private_key == original.private_key


def test_hidden_preshared_key_is_restored_on_edit():
    text = proton_conf().replace("Endpoint =", f"PresharedKey = {make_key()}\nEndpoint =")
    original = parse(text)
    redacted = render(original, hide_private_key=True)
    assert "PresharedKey = [HIDDEN]" in redacted
    edited = parse(redacted, existing_private_key=original.private_key,
                   existing_preshared_key=original.preshared_key)
    assert edited.preshared_key == original.preshared_key


def test_hidden_key_without_existing_key_is_rejected():
    with pytest.raises(ConfigError, match="hidden"):
        parse(render(parse(proton_conf()), hide_private_key=True))


@pytest.mark.parametrize("text, message", [
    ("[Peer]\nPublicKey = x", "Interface"),
    ("[Interface]\nPrivateKey = abc\nAddress = 10.0.0.2/32\n[Peer]\nPublicKey = x", "base64"),
    ("[Interface]\nAddress = 10.0.0.2/32\n[Peer]", "PrivateKey"),
    ("[Interface]\nfoo\n", "Invalid line"),
    ("[Weird]\n", "Unknown section"),
])
def test_invalid_configs(text, message):
    with pytest.raises(ConfigError, match=message):
        parse(text)


def test_multiple_peers_rejected():
    text = proton_conf() + f"\n[Peer]\nPublicKey = {make_key()}\nEndpoint = 1.2.3.4:51820\n"
    with pytest.raises(ConfigError, match="single-peer"):
        parse(text)


@pytest.mark.parametrize("value, host, port", [
    ("1.2.3.4:51820", "1.2.3.4", 51820),
    ("[2001:db8::1]:51820", "2001:db8::1", 51820),
    ("mx-12.protonvpn.net:443", "mx-12.protonvpn.net", 443),
])
def test_endpoints(value, host, port):
    ep = parse_endpoint(value)
    assert (ep.host, ep.port) == (host, port)
    assert str(ep) == value


@pytest.mark.parametrize("value", ["1.2.3.4", "<svg/onload=alert(1)>:80", "[zz::1]:5", "a.b:70000"])
def test_bad_endpoints(value):
    with pytest.raises(ConfigError):
        parse_endpoint(value)


def test_inline_comments_are_stripped():
    cfg = parse(proton_conf().replace("Endpoint = 203.0.113.7:51820",
                                      "Endpoint = 203.0.113.7:51820 # primary"))
    assert str(cfg.endpoint) == "203.0.113.7:51820"


def test_render_roundtrip():
    cfg = parse(proton_conf())
    assert parse(render(cfg)) == cfg


@pytest.mark.parametrize("raw, expected", [
    ("MX-12.conf", "MX-12"),
    ("../../etc/passwd", "etc_passwd"),
    ("wg mexico (1).CONF", "wg_mexico_1"),
])
def test_sanitize_name(raw, expected):
    assert sanitize_name(raw) == expected


def test_sanitize_name_empty():
    with pytest.raises(ConfigError):
        sanitize_name("...conf")
