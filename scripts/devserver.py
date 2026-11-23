"""Run the web app locally (any OS) with a simulated network stack.

    python scripts/devserver.py            # http://127.0.0.1:8080, password "devpassword"

Nothing touches the host: ip/wg/nft calls go to tests/fakes.FakeRunner.
State lives in .devdata/ (delete it to start over).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from tests.fakes import FakeRunner  # noqa: E402

from lobbyshift.app import create_app  # noqa: E402
from lobbyshift.settings import Settings  # noqa: E402


def main() -> None:
    logging.basicConfig(level="INFO", format="%(levelname)s %(name)s: %(message)s")
    data = ROOT / ".devdata"
    settings = Settings(
        data_dir=data,
        legacy_dir=data / "legacy",
        admin_password="devpassword",
        geoip_auto_update=False,
        web_host="127.0.0.1",
    )
    app = create_app(settings, FakeRunner())
    uvicorn.run(app, host=settings.web_host, port=settings.web_port)


if __name__ == "__main__":
    main()
