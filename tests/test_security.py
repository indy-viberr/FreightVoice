"""
Opt-in webhook auth tests.

Covers the security matrix: missing signature rejected, invalid HMAC/token
rejected, valid accepted — and the demo default (no secret) stays open.
"""

from __future__ import annotations

import hashlib
import hmac

import pytest

from freightvoice import config, security


@pytest.fixture()
def token_auth(monkeypatch):
    monkeypatch.setattr(config, "VAPI_WEBHOOK_SECRET", "s3cr3t")
    monkeypatch.setattr(config, "VAPI_AUTH_MODE", "token")
    monkeypatch.setattr(config, "VAPI_SIGNATURE_HEADER", "")


@pytest.fixture()
def hmac_auth(monkeypatch):
    monkeypatch.setattr(config, "VAPI_WEBHOOK_SECRET", "s3cr3t")
    monkeypatch.setattr(config, "VAPI_AUTH_MODE", "hmac")
    monkeypatch.setattr(config, "VAPI_SIGNATURE_HEADER", "")


# --- disabled by default -------------------------------------------------- #
def test_disabled_when_no_secret(monkeypatch):
    monkeypatch.setattr(config, "VAPI_WEBHOOK_SECRET", "")
    assert security.is_enabled() is False
    ok, _ = security.verify({}, b"{}")
    assert ok is True  # demo runs without any header


# --- token mode ----------------------------------------------------------- #
def test_token_valid_accepted(token_auth):
    ok, _ = security.verify({"X-Vapi-Secret": "s3cr3t"}, b"{}")
    assert ok is True


def test_token_missing_rejected(token_auth):
    ok, reason = security.verify({}, b"{}")
    assert ok is False and "missing" in reason


def test_token_wrong_rejected(token_auth):
    ok, reason = security.verify({"X-Vapi-Secret": "nope"}, b"{}")
    assert ok is False and "bad secret" in reason


# --- hmac mode ------------------------------------------------------------ #
def _sig(body: bytes, secret="s3cr3t") -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_hmac_valid_accepted(hmac_auth):
    body = b'{"message":{"type":"tool-calls"}}'
    ok, _ = security.verify({"X-Vapi-Signature": _sig(body)}, body)
    assert ok is True


def test_hmac_valid_with_prefix_accepted(hmac_auth):
    body = b'{"a":1}'
    ok, _ = security.verify({"X-Vapi-Signature": "sha256=" + _sig(body)}, body)
    assert ok is True


def test_hmac_invalid_rejected(hmac_auth):
    body = b'{"a":1}'
    ok, reason = security.verify({"X-Vapi-Signature": _sig(b"tampered")}, body)
    assert ok is False and "bad signature" in reason


def test_hmac_missing_rejected(hmac_auth):
    ok, reason = security.verify({}, b"{}")
    assert ok is False and "missing" in reason


def test_custom_header_name_respected(monkeypatch):
    monkeypatch.setattr(config, "VAPI_WEBHOOK_SECRET", "s3cr3t")
    monkeypatch.setattr(config, "VAPI_AUTH_MODE", "token")
    monkeypatch.setattr(config, "VAPI_SIGNATURE_HEADER", "X-My-Auth")
    assert security.verify({"X-My-Auth": "s3cr3t"}, b"{}")[0] is True
    assert security.verify({"X-Vapi-Secret": "s3cr3t"}, b"{}")[0] is False


# --- integration: guard wired into the app -------------------------------- #
@pytest.fixture()
def authed_client(faketms_server, monkeypatch):
    from freightvoice import store
    monkeypatch.setattr(config, "FAKETMS_URL", faketms_server)
    monkeypatch.setattr(config, "VAPI_WEBHOOK_SECRET", "s3cr3t")
    monkeypatch.setattr(config, "VAPI_AUTH_MODE", "token")
    monkeypatch.setattr(config, "VAPI_SIGNATURE_HEADER", "")
    store.reset()
    from freightvoice.app import create_app
    app = create_app()
    app.testing = True
    return app.test_client()


def _body():
    return {"message": {"type": "tool-calls", "toolCalls": [
        {"id": "a", "type": "function",
         "function": {"name": "get_load_context", "arguments": {"load_id": "L1001"}}}]}}


def test_app_rejects_unauthenticated_webhook(authed_client):
    resp = authed_client.post("/webhook/get_load_context", json=_body())
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "unauthorized"


def test_app_accepts_authenticated_webhook(authed_client):
    resp = authed_client.post("/webhook/get_load_context", json=_body(),
                              headers={"X-Vapi-Secret": "s3cr3t"})
    assert resp.status_code == 200
    assert "results" in resp.get_json()


def test_dashboard_stays_open_under_auth(authed_client):
    # Health/state aren't webhooks — they must not require the secret.
    assert authed_client.get("/health").status_code == 200
    assert authed_client.get("/api/state").status_code == 200
