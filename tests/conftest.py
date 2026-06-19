from __future__ import annotations

from collections.abc import Callable, Generator
from threading import Thread
from typing import Any

import pytest
import requests
from flask import Flask
from werkzeug.serving import make_server

from faketms.app import create_app as create_faketms_app
from freightvoice.app import create_app as create_freightvoice_app


@pytest.fixture
def fake_tms_app(tmp_path: Any) -> Flask:
    return create_faketms_app({"DATABASE_URL": f"sqlite:///{tmp_path / 'faketms-direct.sqlite3'}"})


@pytest.fixture
def fake_tms_server(tmp_path: Any) -> Generator[str, None, None]:
    app = create_faketms_app({"DATABASE_URL": f"sqlite:///{tmp_path / 'faketms.sqlite3'}"})
    server = make_server("127.0.0.1", 0, app)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        yield url
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture
def app(fake_tms_server: str) -> Flask:
    return create_freightvoice_app(
        {
            "TESTING": True,
            "FAKETMS_URL": fake_tms_server,
            "FREIGHTVOICE_TMS": "fake",
            "FREIGHTVOICE_FACTORING": "fake",
            "WEBHOOK_SECRET": "",
        }
    )


@pytest.fixture
def client(app: Flask) -> Any:
    return app.test_client()


@pytest.fixture
def fake_tms_state(fake_tms_server: str) -> Callable[[], dict[str, Any]]:
    def _state() -> dict[str, Any]:
        response = requests.get(f"{fake_tms_server}/state", timeout=5)
        response.raise_for_status()
        return response.json()

    return _state


@pytest.fixture
def seeded_loads() -> list[str]:
    return ["FV-DEMO-001", "FV-DEMO-002", "FV-DEMO-003"]


def vapi_envelope(tool_call_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "message": {
            "type": "tool-calls",
            "toolCalls": [
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }
            ],
        }
    }

