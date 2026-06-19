"""
Test harness.

The webhook/e2e tests exercise the *real* path: freightvoice -> FakeTMSAdapter ->
faketms over HTTP. To keep that honest while staying localhost-only, we boot the
faketms Flask app on an ephemeral port in a background thread, point
``config.FAKETMS_URL`` at it, then drive freightvoice through its Flask test
client.
"""

from __future__ import annotations

import socket
import threading

import pytest
from werkzeug.serving import make_server

from faketms.app import create_app as create_faketms
from freightvoice import config, store


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture()
def faketms_server():
    """Run faketms on a real localhost port for the duration of a test."""
    port = _free_port()
    app = create_faketms()  # init_db(reset=True) reseeds the three demo loads
    server = make_server("127.0.0.1", port, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    thread.join(timeout=2)


@pytest.fixture()
def client(faketms_server, monkeypatch):
    """A freightvoice test client wired to the live faketms server."""
    monkeypatch.setattr(config, "FAKETMS_URL", faketms_server)
    store.reset()
    # Import here so the app picks up the patched config when building adapters.
    from freightvoice.app import create_app

    app = create_app()
    app.testing = True
    return app.test_client()
