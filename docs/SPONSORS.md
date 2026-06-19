# FreightVoice — sponsor tools (for judges)

FreightVoice uses **all three sponsor tools**, each on a distinct layer of the
stack. This doc is deliberately precise about **what is actually running** vs.
what is wired-but-needs-config vs. what is roadmap — because overclaiming is the
fastest way to lose a judge's trust.

```
        ☎  Driver calls after a delivery
        │
   ┌────▼─────────────────────────────────────────────┐
   │  VAPI        voice layer — ASR + TTS + tool calls  │   sponsor #1
   └────┬─────────────────────────────────────────────┘
        │
   ┌────▼─────────────────────────────────────────────┐
   │  NEBIUS      the LLM brain behind Vapi (BYOK)      │   sponsor #2
   └────┬─────────────────────────────────────────────┘
        │  structured tool-call args
   ┌────▼─────────────────────────────────────────────┐
   │  FreightVoice middleware (the product)             │
   │  webhooks · validation · discrepancy engine        │
   └────┬─────────────────────────────────────────────┘
        │
   ┌────▼─────────────────────────────────────────────┐
   │  INSFORGE    system of record — Postgres + REST     │   sponsor #3
   └──────────────────────────────────────────────────┘
```

## Legend

- 🟢 **REAL & LIVE** — running and verified by us.
- 🟡 **WIRED, not live** — integration code/config exists and is correct, but it
  needs an external account/dashboard step to actually run (we have not verified
  the live form here), or it's an intentionally inert stub/seam.
- 🔴 **ROADMAP** — documented direction only; no code, not running.

## Status at a glance

| Capability | Sponsor | Status |
|---|---|---|
| TMS system-of-record (loads / PODs / exception queue in Postgres) | **InsForge** | 🟢 REAL & LIVE — verified end-to-end |
| Middleware: webhooks, validation, discrepancy engine, dashboard | *(ours)* | 🟢 REAL & LIVE — 89 passing tests |
| Vapi webhook contract (server-tool envelope) | **Vapi** | 🟢 REAL & LIVE — verified with Vapi-shaped payloads |
| Live phone call (telephony → assistant → webhooks) | **Vapi** | 🟡 WIRED — needs Vapi dashboard config; not verified here |
| LLM brain (custom-LLM / BYOK) | **Nebius** | 🟡 WIRED — verified config recipe; runs in Vapi, not our code |
| Webhook HMAC / token auth | **Vapi** | 🟡 WIRED — opt-in, off by default |
| Real carrier TMS (Samsara / Motive / RTS) | — | 🟡 WIRED — adapter stubs (`NotImplementedError`) |
| Fine-tuned model `FreightVoice-FT-v1` | **Nebius** | 🔴 ROADMAP — reference SFT script, never run |
| pgvector RAG evidence layer | **InsForge** | 🔴 ROADMAP — documented, no code |
| Invoice extraction · HIL · reconciliation · audit log | InsForge + Nebius | 🔴 ROADMAP — documented, no code |

---

## 🟢 What's REAL & LIVE

### InsForge — the system of record (verified)

With `FAKETMS_STORAGE=insforge`, the carrier TMS keeps **no local data** — loads,
PODs, and the exception queue all live in **InsForge Postgres**, accessed through
InsForge's auto-generated PostgREST API (`Authorization: Bearer ik_…`). Three
tables: `loads`, `pods`, `discrepancies` (DDL in
[`migrations/`](../migrations/), applied via `@insforge/cli`).

During a call, these hit InsForge in real time:
- look up load → `GET /api/database/records/loads?load_id=eq.<id>`
- record POD → `POST …/pods` + `PATCH …/loads?…&status=eq.pending` (→ delivered)
- exceptions → `POST …/discrepancies` (severity preserved)
- clean load → `PATCH …/loads` (→ invoiced, with invoice number)
- dashboard → reads all three tables every 2s

**How we know it's live:** we ran the full call simulation against
`FAKETMS_STORAGE=insforge` and then queried InsForge **directly** (outside our
app): `L1001` invoiced, `L2002`/`L3003` held with the correct discrepancies, 3
PODs persisted. Re-verify anytime with `python scripts/check_insforge.py`.
Code: [`faketms/stores/insforge_store.py`](../faketms/stores/insforge_store.py).

### The middleware (verified)

The webhooks, the pydantic validation, the per-trigger discrepancy engine, and
the live dashboard are the actual product and run today — **89 passing tests**
(`pytest`), including schema, discrepancy-engine, webhook-contract, and
end-to-end suites. This is the "the middleware is real; only the carrier is
mocked" claim, and it holds.

### Vapi webhook contract (verified with Vapi-shaped payloads)

The four webhooks implement Vapi's exact server-tool envelope — a
`message.toolCalls[]` array in, a `results[]` array keyed by `toolCallId` out
([`freightvoice/vapi.py`](../freightvoice/vapi.py)). `demo/simulate_call.py`
posts **real Vapi-shaped payloads** to the live endpoints, and the webhook tests
assert the envelope. So the *contract* a real Vapi call would use is real and
exercised today — see the WIRED note below for the live-telephony piece.

---

## 🟡 What's WIRED, but not live

### Vapi — the live phone call

Everything needed to place a real call is written down in
[`VAPI_SETUP.md`](VAPI_SETUP.md): the assistant system prompt, the four tool
definitions, and the server URLs. **What makes it "live" is external to this
repo** — a Vapi account, the assistant configured in the Vapi dashboard, and a
public tunnel (e.g. `ngrok http 5000`) so Vapi can reach the webhooks. We have
**not** verified a real telephony call here; the contract side is verified, the
dashboard side is yours to confirm before claiming it on stage.

### Nebius — the LLM brain (config seam, by design)

Nebius runs the agent's LLM via Vapi's OpenAI-compatible **custom-LLM (BYOK)**
provider — Vapi calls Nebius directly. **By design there is no inference code in
our middleware** (a Vapi app receives already-structured tool args), so this is a
*configuration*, not running code in this repo. The recipe is verified-correct:
base URL `https://api.tokenfactory.nebius.com/v1/`, model
`Qwen/Qwen3-30B-A3B-Instruct-2507` (MoE, tool-use optimized; `…-8B-Instruct-fast`
fallback), Nebius key as the Vapi BYOK credential ([`VAPI_SETUP.md` §3](VAPI_SETUP.md)).
It is "live" only once configured in your Vapi dashboard — not verified here.

### Webhook authentication (opt-in)

HMAC / shared-secret verification of incoming webhooks is implemented
([`freightvoice/security.py`](../freightvoice/security.py)) and tested, but
**off by default** so the demo runs account-free. Set `VAPI_WEBHOOK_SECRET` to
turn it on.

### Real carrier TMS adapters

`SamsaraAdapter` / `MotiveAdapter` / `RTSFactoringAdapter` exist as real
interfaces against the production seam, but every method `raise
NotImplementedError` — they prove the seam, they don't run. Going live = implement
one class + set `FREIGHTVOICE_TMS`. (For the demo, InsForge backs the *fake* TMS.)

---

## 🔴 What's ROADMAP (not wired, not live)

Documented direction, no code today — the FreightLedger expansion:

- **`FreightVoice-FT-v1` fine-tune (Nebius).** A reference SFT script is included
  in [`VAPI_SETUP.md` §4](VAPI_SETUP.md) but is **never invoked** and has no
  dataset. Today the base instruct model runs the demo.
- **pgvector RAG evidence (InsForge).** The same InsForge project would host the
  vector store for reconciliation evidence, filtered by `load_id` / `source_type`.
  No code yet.
- **Invoice extraction · HIL · reconciliation · durable audit log.** OCR/extraction
  workers (Nebius strict-JSON), human-in-the-loop review, and audit trails —
  documented in the README's Batch B section, not built.

---

## The honest one-paragraph version

> Three sponsors, three layers. **InsForge is live** — it's the real Postgres
> system-of-record behind our TMS, and we verified the full pipeline persists to
> it. **Vapi is real at the contract layer** (our webhooks speak its exact
> protocol, verified with Vapi-shaped payloads); a live phone call just needs the
> Vapi dashboard wired up. **Nebius is the LLM brain by configuration** — Vapi
> calls it via BYOK custom-LLM, which is the correct architecture (no inference in
> our middleware). Everything past that — fine-tuning, RAG, reconciliation — is
> documented roadmap, and we say so.

## Running the live (InsForge) demo

See [`TEAMMATE_SETUP.md`](TEAMMATE_SETUP.md). Short version: put the InsForge
creds in a gitignored `.env` (`FAKETMS_STORAGE=insforge` + URL + `ik_` token),
run `python scripts/check_insforge.py` to confirm ✓, then `make demo`. The
default `make demo` (no `.env`) runs account-free on SQLite.
