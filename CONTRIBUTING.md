# Contributing to LobbyShift

Thanks for your interest in contributing! 🎮

## How to Contribute

### Reporting Bugs

- Check if the issue already exists
- Include your OS, install method (native / Docker), and the output of `sudo lobbyshift doctor`
- Add relevant logs: `journalctl -u lobbyshift -e` or `docker compose logs lobbyshift`
- Describe steps to reproduce

### Suggesting Features

- Open an issue with `[Feature]` prefix
- Describe the use case and expected behavior

### Pull Requests

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes, with tests
4. Run `ruff check src tests scripts` and `pytest`
5. Commit with clear messages
6. Push and create a PR (CI runs lint, tests on Python 3.11–3.13, shellcheck and a Docker build)

## Development Setup

Development works on any OS, including Windows and macOS: a fake network
stack replaces `ip`/`wg`/`nft`, so nothing touches your machine.

```bash
git clone https://github.com/Smokimcpot/LobbyShift.git
cd LobbyShift
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

pytest                             # full test suite
python scripts/devserver.py        # UI on http://127.0.0.1:8080, password "devpassword"
```

## Project Layout

```
src/lobbyshift/
├── app.py              FastAPI factory, security middleware (CSP, Origin check)
├── api/routes.py       HTTP endpoints
├── service.py          Orchestrator: connect/disconnect, watchdog, migration from v1
├── core/
│   ├── wgconfig.py     WireGuard config parser (allowlist: PostUp & co. are dropped)
│   ├── tunnel.py       ip link / wg setconf / policy routing (no wg-quick)
│   ├── firewall.py     nftables ruleset (atomic), Docker FORWARD compatibility
│   ├── geoip.py        Offline DB-IP country database
│   └── health.py       Latency probes
├── providers/proton.py Proton VPN config metadata and advice
├── store.py            SQLite persistence
├── auth.py             Password, sessions, CLI token
├── cli.py              `lobbyshift` command
└── web/                UI (static ES modules, no build step)
tests/                  pytest suite + FakeRunner
packaging/              systemd unit, example config
```

## Design Rules

- **Never execute user-provided content.** WireGuard configs go through
  `core/wgconfig.parse`, which keeps an allowlist of keys.
- **No root.** The service runs with `CAP_NET_ADMIN` + `CAP_NET_RAW` only.
- **Every system command goes through `Runner`** so it can be faked in tests.
- **The UI never injects data as HTML.** It must work under the strict CSP set in `app.py`.

## Code Style

- `ruff` (config in `pyproject.toml`)
- Type hints and docstrings for non-obvious behavior
- Keep functions small and focused

## Areas We Need Help

- 🌐 More VPN provider integrations (`src/lobbyshift/providers/`)
- 🌍 Translations
- 🧪 Testing on more hardware (Pi 3, Pi 5, x86 mini PCs)

## Code of Conduct

Be respectful. We're all here to have fun gaming with fair lobbies.

## Questions?

Open an issue or join discussions.
