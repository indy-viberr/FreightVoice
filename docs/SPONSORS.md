# FreightVoice — sponsor tools (for judges)

FreightVoice uses **all three sponsor tools**, each on a distinct layer of the
stack — and we've now run the **whole pipeline live: a real phone call on Vapi,
driven by the Nebius LLM, calling our tools, persisting to InsForge.** This doc
is precise about what is actually running vs. what is wired-but-optional vs. what
is roadmap, because overclaiming is the fastest way to lose a judge's trust.

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

- 🟢 **REAL & LIVE** — running and verified by us (automated tests and/or a live
  end-to-end run).
- 🟡 **WIRED, optional** — integration code exists and is correct, but it's an
  intentionally inert stub/seam or an opt-in feature that's off by default.
- 🔴 **ROADMAP** — documented direction only; no code, not running.

## Status at a glance

| Capability | Sponsor | Status |
|---|---|---|
| Live phone call (telephony → assistant → tools) | **Vapi** | 🟢 REAL & LIVE — demonstrated on a real call |
| LLM brain (custom-LLM / BYOK) drives the conversation | **Nebius** | 🟢 REAL & LIVE — drove a real call |
| Vapi webhook contract (server-tool envelope) | **Vapi** | 🟢 REAL & LIVE — live call + tests |
| TMS system-of-record (loads / PODs / exception queue in Postgres) | **InsForge** | 🟢 REAL & LIVE — verified end-to-end |
| Middleware: webhooks, validation, discrepancy engine, dashboard | *(ours)* | 🟢 REAL & LIVE — 89 passing tests |
| Webhook HMAC / token auth | **Vapi** | 🟡 WIRED — opt-in, off by default |
| Real carrier TMS (Samsara / Motive / RTS) | — | 🟡 WIRED — adapter stubs (`NotImplementedError`) |
| Fine-tuned model `FreightVoice-FT-v1` | **Nebius** | 🔴 ROADMAP — reference SFT script, never run |
| pgvector RAG evidence layer | **InsForge** | 🔴 ROADMAP — documented, no code |
| Invoice extraction · HIL · reconciliation · audit log | InsForge + Nebius | 🔴 ROADMAP — documented, no code |

---

## 🟢 What's REAL & LIVE

The end-to-end path has been demonstrated with a real phone call: a driver speaks
to the Vapi number, **Nebius** drives the conversation and emits tool calls,
**Vapi** invokes our **webhooks**, the **middleware** validates + runs the
discrepancy engine, and the result **persists to InsForge** — with the dashboard
updating as it happens. Each layer:

### Vapi — voice + the live call

Vapi runs the phone call (speech-to-text, text-to-speech, turn-taking) and
invokes our four webhooks as *server tools*. The webhooks implement Vapi's exact
envelope — `message.toolCalls[]` in, `results[]` keyed by `toolCallId` out
([`freightvoice/vapi.py`](../freightvoice/vapi.py)). Verified two ways: a **live
call** placed through the Vapi assistant (system prompt + tool defs from
[`VAPI_SETUP.md`](VAPI_SETUP.md)), **and** the webhook-contract tests +
`demo/simulate_call.py` posting real Vapi-shaped payloads.

### Nebius — the LLM brain (live, via BYOK)

The conversation is driven by a model on **Nebius Token Factory**, called through
Vapi's OpenAI-compatible **custom-LLM (BYOK)** provider — Vapi calls Nebius
directly, so **by design there is no inference code in our middleware**; we
receive already-structured tool args. This drove the live call. Config (verified
recipe) in [`VAPI_SETUP.md` §3](VAPI_SETUP.md): base URL
`https://api.tokenfactory.nebius.com/v1/`, BYOK key in Vapi's Provider Keys, with
`Qwen/Qwen3-30B-A3B-Instruct-2507` (MoE, tool-use optimized) recommended for
voice latency.

### InsForge — the system of record (verified)

With `FAKETMS_STORAGE=insforge`, the carrier TMS keeps **no local data** — loads,
PODs, and the exception queue all live in **InsForge Postgres**, via InsForge's
auto-generated PostgREST API (`Authorization: Bearer ik_…`). Tables `loads`,
`pods`, `discrepancies` (DDL in [`migrations/`](../migrations/), applied via
`@insforge/cli`).

During a call these hit InsForge in real time:
- look up load → `GET /api/database/records/loads?load_id=eq.<id>`
- record POD → `POST …/pods` + `PATCH …/loads?…&status=eq.pending` (→ delivered)
- exceptions → `POST …/discrepancies` (severity preserved)
- clean load → `PATCH …/loads` (→ invoiced, with invoice number)
- dashboard → reads all three tables every 2s

**How we know:** we ran the full simulation against InsForge and queried it
**directly** (outside our app) — `L1001` invoiced, `L2002`/`L3003` held with the
right discrepancies, 3 PODs persisted. Re-verify with
`python scripts/check_insforge.py`. Code:
[`faketms/stores/insforge_store.py`](../faketms/stores/insforge_store.py).

### The middleware (verified)

The webhooks, pydantic validation, the per-trigger discrepancy engine, and the
live dashboard are the product and run today — **89 passing tests** (schema,
discrepancy-engine, webhook-contract, end-to-end). "The middleware is real; only
the carrier-specific logic is mocked" holds.

---

## 🟡 What's WIRED, but optional / inert

- **Webhook authentication.** HMAC / shared-secret verification of incoming
  webhooks is implemented ([`freightvoice/security.py`](../freightvoice/security.py))
  and tested, but **off by default** so the demo runs account-free. Enable with
  `VAPI_WEBHOOK_SECRET`.
- **Real carrier TMS adapters.** `SamsaraAdapter` / `MotiveAdapter` /
  `RTSFactoringAdapter` are real interfaces against the production seam, but every
  method `raise NotImplementedError` — they prove the seam, they don't run. Going
  live = implement one class + set `FREIGHTVOICE_TMS`. (For the demo, InsForge
  backs the *fake* TMS.)

---

## 🔴 What's ROADMAP (not wired, not live)

Documented direction, no code today — the FreightLedger expansion:

- **`FreightVoice-FT-v1` fine-tune (Nebius).** A reference SFT script is in
  [`VAPI_SETUP.md` §4](VAPI_SETUP.md) but is **never invoked** and has no dataset.
  The live call uses the base instruct model.
- **pgvector RAG evidence (InsForge).** The same InsForge project would host the
  vector store for reconciliation evidence, filtered by `load_id` / `source_type`.
  No code yet.
- **Invoice extraction · HIL · reconciliation · durable audit log.** Documented in
  the README's Batch B section, not built.

---

## The honest one-paragraph version

> Three sponsors, three layers, demonstrated live end-to-end. A driver calls a
> **Vapi** number; **Nebius** is the LLM brain that runs the conversation (via
> BYOK custom-LLM — the correct architecture, no inference in our middleware) and
> emits tool calls; Vapi invokes our real webhooks; and the result persists to
> **InsForge** Postgres, our live system of record, with the dashboard updating in
> real time. Everything past that — fine-tuning, RAG, reconciliation — is
> documented roadmap, and we say so.

## Running the live (InsForge) demo

See [`TEAMMATE_SETUP.md`](TEAMMATE_SETUP.md). Short version: put the InsForge
creds in a gitignored `.env` (`FAKETMS_STORAGE=insforge` + URL + `ik_` token), run
`python scripts/check_insforge.py` to confirm ✓, then `make demo`. The default
`make demo` (no `.env`) runs account-free on SQLite. For the voice + LLM side, the
Vapi assistant and Nebius BYOK key are configured in the Vapi dashboard per
[`VAPI_SETUP.md`](VAPI_SETUP.md).
