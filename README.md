# FreightVoice

**Voice-captured proof of delivery for freight carriers.** A truck driver calls
a phone number after a delivery. [Vapi](https://vapi.ai) runs the voice — speech,
LLM, text-to-speech — and calls FreightVoice's webhooks to pull the load and push
the completed delivery. FreightVoice validates the record, runs a discrepancy
engine, writes the POD back to the carrier's TMS, and auto-invoices when it's
clean. A live dashboard shows every captured POD as it lands.

> **The honest boundary:** everything in `freightvoice/` is the production
> webhook path. The only mock is the carrier's TMS (`faketms/`), and that's one
> interface away from real — implement `SamsaraAdapter` and change one env var.

---

## 30-second quickstart

```bash
make demo        # boots fake TMS (:5001) + middleware/dashboard (:5000), seeded
```

Then, in a second terminal:

```bash
open http://127.0.0.1:5000          # the dashboard (projector view)
make simulate                       # replay the 3 seeded loads through the webhooks
```

You'll watch three loads move **pending → delivered → invoiced** (or get **held
for review**) on the dashboard in real time. No phone, no accounts, no paid
services required.

```bash
make test        # 40 tests, localhost only
```

First run creates a virtualenv and installs Flask / pydantic / requests / pytest.

---

## Architecture

```
Vapi (real, configured in the Vapi dashboard — NOT built here)
   │  HTTPS webhook calls during the live call
   ▼
┌─────────────────────────────────────┐
│  freightvoice/  (Flask, :5000)       │   ← REAL. This is the product.
│   webhook endpoints (Vapi-facing)    │
│   validation + discrepancy engine    │
│   pydantic schemas (load / POD / acc)│
│   TMSAdapter / FactoringAdapter      │   ← the seam
│   dashboard (POD log, live)          │
└──────────────┬──────────────────────┘
               │ HTTP, via FakeTMSAdapter
               ▼
┌─────────────────────────────────────┐
│  faketms/  (Flask, :5001)            │   ← FAKE, behaves like a real TMS
│   seeded demo loads (SQLite)         │
│   GET /loads/<id>, POST /pod, …      │
└─────────────────────────────────────┘
```

`freightvoice/` contains **nothing carrier-specific**. It depends only on the
abstract `TMSAdapter` / `FactoringAdapter` interfaces in
[`freightvoice/adapters/base.py`](freightvoice/adapters/base.py). Two concrete
TMS adapters ship:

- **`FakeTMSAdapter`** — real, working; talks HTTP to the `faketms` service. Used in the demo.
- **`SamsaraAdapter`** (+ `MotiveAdapter`, `RTSFactoringAdapter`) — stubs that name the real REST endpoints and `raise NotImplementedError`. They exist to prove the seam, not to run.

The adapter is chosen by `FREIGHTVOICE_TMS=fake|samsara|motive`.

---

## The webhook contract (what Vapi calls)

Vapi invokes these as server tools — a `message.toolCalls[]` envelope in, a
`results[]` array keyed by `toolCallId` out (see
[`freightvoice/vapi.py`](freightvoice/vapi.py)).

| Endpoint | What it does |
|---|---|
| `POST /webhook/get_load_context`   | `adapter.get_load(load_id)` → returns `LoadContext` so the agent confirms, not dictates. Unknown load → tells the agent to have the driver re-read the number. |
| `POST /webhook/push_delivery_record` | validate → discrepancy engine → `write_pod` → if clean, `trigger_invoice` + factoring advance. Returns a spoken readback. |
| `POST /webhook/flag_discrepancy`   | explicit escalation to the exception queue, with a transcript excerpt. |
| `POST /webhook/schedule_callback`  | records a callback intent (driver dropped). No real outbound dialing. |

Plus the dashboard: `GET /` and `GET /api/state` (polled every 2s).

### The discrepancy engine

[`freightvoice/validation.py`](freightvoice/validation.py) — pure, tested
functions. Each trigger carries **its own severity** (never one generic flag):

| Trigger | Severity |
|---|---|
| weight variance > 5% (configurable) | `warning` (→ `critical` if > 15%) |
| piece count short vs expected | `critical` |
| piece count over | `warning` |
| damage reported | `critical` |
| exception ∈ {refused, short, redelivery} | `critical` |
| missing recipient name | `warning` |

A clean record returns `[]` and proceeds straight to invoicing.

### The three seeded loads

| Load | Scenario | Result |
|---|---|---|
| `L1001` | actuals match | clean → **invoiced** |
| `L2002` | weight ~13% under | **held** (weight_variance) |
| `L3003` | damage + refused | **held** (damage + exception) |

---

## The LLM seam

The fine-tuned LLM lives inside Vapi's config, not this codebase — the webhooks
receive already-structured tool-call args, so there is **no inference in the
middleware**. [`docs/VAPI_SETUP.md`](docs/VAPI_SETUP.md) contains the assistant
system prompt (confirm-don't-dictate, closed questions, explicit readback,
graceful retry), the four tool definitions, the Nebius custom-LLM `base_url`
block, and the `FreightVoice-FT-v1` fine-tuning script as a documented future
seam.

---

## Going to production

1. Implement `SamsaraAdapter` (or `MotiveAdapter`) in
   [`freightvoice/adapters/`](freightvoice/adapters/) — four methods, endpoints
   already named in the docstrings.
2. Set `FREIGHTVOICE_TMS=samsara` and provide the API token.
3. Deploy `freightvoice/`, point the Vapi tool URLs (`docs/VAPI_SETUP.md`) at the
   deployed host.

That's the list. Nothing in `freightvoice/` changes.

---

## Tech & layout

Python 3.11+, Flask, **stdlib `sqlite3`** (no ORM), `requests`, `pydantic` v2 for
schemas/validation, `pytest`.

```
freightvoice/        the product (webhooks, validation, schemas, adapters, dashboard)
  adapters/          base ABCs + fake (working) + samsara/motive/rts (stubs)
faketms/             the only mock — seeded SQLite TMS
demo/simulate_call.py replay the 3 loads without a phone
docs/VAPI_SETUP.md   Vapi assistant prompt, tools, Nebius block, SFT script
tests/               schema, discrepancy, webhook-contract, end-to-end
```

## Compliance note (stated once)

For a real deployment, the call is handled under an FMCSA-aligned posture:
driver consent captured at call start and zero-retention of raw audio (Vapi
configured to not persist recordings; FreightVoice stores only the structured
record and a short transcript excerpt for the discrepancy it documents). This is
a configuration and policy matter, not runtime behavior in this demo.

Performance targets in the PRD (latency, word-error-rate, extraction accuracy)
are **targets**, not measured claims — they are deliberately not asserted as fact
here.
