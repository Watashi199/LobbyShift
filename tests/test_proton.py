import pytest

from lobbyshift.core.geoip import flag
from lobbyshift.core.wgconfig import parse
from lobbyshift.providers import detect, proton

from .conftest import make_key, proton_conf


@pytest.mark.parametrize("server, exit_country, entry, secure_core", [
    ("MX#12", "MX", None, False),
    ("CH-JP#3", "JP", "CH", True),
    ("IS-US#1", "US", "IS", True),
    ("US-CA#45", "US", None, False),  # US state, not Secure Core
    ("SE#7", "SE", None, False),
])
def test_server_name_parsing(server, exit_country, entry, secure_core):
    meta = proton.metadata(parse(proton_conf(server=server)))
    assert meta["country"] == exit_country
    assert meta["entry_country"] == entry
    assert meta["secure_core"] is secure_core


def test_detect_proton_and_features():
    provider, meta = detect(parse(proton_conf(moderate_nat="off")))
    assert provider == "proton"
    assert meta["features"]["moderate_nat"] == "off"
    assert "moderate_nat_off" in {a["code"] for a in meta["advice"]}


def test_secure_core_advice():
    _, meta = detect(parse(proton_conf(server="CH-JP#3")))
    assert "secure_core" in {a["code"] for a in meta["advice"]}


def test_generic_config_is_custom():
    text = (f"[Interface]\nPrivateKey = {make_key()}\nAddress = 10.66.0.2/32\n"
            f"[Peer]\nPublicKey = {make_key()}\nEndpoint = 198.51.100.4:51820\n")
    assert detect(parse(text)) == ("custom", {})


@pytest.mark.parametrize("code, expected", [("FR", "🇫🇷"), ("uk", "🇬🇧"), ("??", "🌐")])
def test_flag(code, expected):
    assert flag(code) == expected
