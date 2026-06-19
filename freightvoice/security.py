"""
Opt-in authentication for the Vapi-facing webhooks.

DISABLED by default: with no ``VAPI_WEBHOOK_SECRET`` set, every request passes so
the zero-account demo runs untouched. Set the secret to require authentication on
every ``/webhook/*`` call.

Two modes:

* ``token`` (default) — shared-secret header equality. Vapi sends the value you
  configure as the assistant/server ``secret`` in a header; Vapi's documented
  default header is ``X-Vapi-Secret``. We compare it to our secret in constant
  time.
* ``hmac`` — HMAC-SHA256 over the raw request body, hex-encoded, compared to a
  signature header (optionally ``sha256=`` prefixed).

IMPORTANT (house rule: don't confidently guess vendor API shapes): Vapi's exact
header name and whether it offers native body-HMAC has varied across versions.
The header is configurable via ``VAPI_SIGNATURE_HEADER`` for exactly that reason.
Confirm against https://docs.vapi.ai/server-url#authentication before enabling in
production, and set the header/mode to match what your Vapi account actually
sends.
"""

from __future__ import annotations

import hashlib
import hmac

from . import config

_DEFAULT_HEADER = {"token": "X-Vapi-Secret", "hmac": "X-Vapi-Signature"}


def is_enabled() -> bool:
    return bool(config.VAPI_WEBHOOK_SECRET)


def _header_name() -> str:
    if config.VAPI_SIGNATURE_HEADER:
        return config.VAPI_SIGNATURE_HEADER
    return _DEFAULT_HEADER.get(config.VAPI_AUTH_MODE, "X-Vapi-Secret")


def verify(headers, raw_body: bytes) -> tuple[bool, str]:
    """Return ``(ok, reason)`` for an inbound webhook request.

    ``headers`` is anything with a case-insensitive ``.get`` (Flask's
    ``request.headers`` qualifies). Pure and side-effect free so it's unit
    testable without a live server.
    """
    if not is_enabled():
        return True, "auth disabled"

    secret = config.VAPI_WEBHOOK_SECRET
    provided = headers.get(_header_name())
    if not provided:
        return False, f"missing {_header_name()} header"

    mode = config.VAPI_AUTH_MODE
    if mode == "hmac":
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        candidate = provided.split("=", 1)[1] if provided.startswith("sha256=") else provided
        ok = hmac.compare_digest(expected, candidate.strip())
        return (ok, "ok" if ok else "bad signature")

    # token mode (default): constant-time equality of the shared secret.
    ok = hmac.compare_digest(secret, provided.strip())
    return (ok, "ok" if ok else "bad secret")
