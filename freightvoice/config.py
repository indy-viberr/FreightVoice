"""Runtime configuration for FreightVoice, all via environment variables.

Nothing here is carrier-specific beyond *which* adapter to instantiate — that is
the entire switch-to-production story: set ``FREIGHTVOICE_TMS=samsara`` and
provide the credential, implement the adapter, done.
"""

from __future__ import annotations

import os


# Which TMS adapter to use: fake | samsara | motive | rts
TMS_BACKEND = os.environ.get("FREIGHTVOICE_TMS", "fake").lower()

# Where the fake TMS lives (only used by FakeTMSAdapter).
FAKETMS_URL = os.environ.get("FAKETMS_URL", "http://127.0.0.1:5001")

# Weight variance tolerance, percent. Mirrors validation.DiscrepancyConfig.
WEIGHT_TOLERANCE_PCT = float(os.environ.get("FREIGHTVOICE_WEIGHT_TOLERANCE_PCT", "5"))

# Whether to fire the factoring advance on a clean delivery.
FACTORING_ENABLED = os.environ.get("FREIGHTVOICE_FACTORING", "fake").lower() != "off"

# Outbound HTTP timeout (seconds) for service-to-service calls.
HTTP_TIMEOUT = float(os.environ.get("FREIGHTVOICE_HTTP_TIMEOUT", "5"))
