# FreightVoice — sponsor tools (for judges)

FreightVoice uses **all three sponsor tools**, and they aren't bolted on — each
owns a distinct, load-bearing layer of the stack. A truck driver's phone call
flows top to bottom:

```
        ☎  Driver calls after a delivery
        │
   ┌────▼─────────────────────────────────────────────┐
   │  VAPI        voice layer — ASR + TTS + tool-call   │   sponsor #1
   │              orchestration during the live call    │
   └────┬─────────────────────────────────────────────┘
        │  invokes our webhooks as "server tools"
   ┌────▼─────────────────────────────────────────────┐
   │  NEBIUS      the LLM brain behind Vapi (custom-LLM │   sponsor #2
   │              / BYOK) — turns speech into structured │
   │              tool calls                             │
   └────┬─────────────────────────────────────────────┘
        │  structured tool-call args
   ┌────▼─────────────────────────────────────────────┐
   │  FreightVoice middleware  (the product — REAL)     │
   │  webhooks · validation · discrepancy engine        │
   └────┬─────────────────────────────────────────────┘
        │  via the storage seam
   ┌────▼─────────────────────────────────────────────┐
   │  INSFORGE    system of record — managed Postgres + │   sponsor #3
   │              auto REST API (the carrier TMS data)   │
   └──────────────────────────────────────────────────┘
```

Voice → brain → product → data. One sponsor per layer.

We've tried to be precise about **what is a live integration vs. a configuration
seam**, because the architecture deliberately separates them — and overclaiming
would be the wrong thing to put in front of judges.

---

## 1. Vapi — the voice layer

**What it does:** runs the actual phone call — speech-to-text, text-to-speech,
turn-taking — and calls FreightVoice's four webhooks as Vapi *server tools*
during the conversation.

**How we use it (in code):**
- The four webhooks (`/webhook/get_load_context`, `push_delivery_record`,
  `flag_discrepancy`, `schedule_callback`) implement **Vapi's exact tool-call
  envelope** — a `message.toolCalls[]` array in, a `results[]` array keyed by
  `toolCallId` out. See [`freightvoice/vapi.py`](../freightvoice/vapi.py) and
  [`freightvoice/app.py`](../freightvoice/app.py).
- The assistant system prompt, the four tool definitions, and the server URLs
  are all in [`VAPI_SETUP.md`](VAPI_SETUP.md) — paste-ready into the Vapi
  dashboard.
- Optional opt-in **webhook authentication** (`X-Vapi-Secret` / HMAC) is
  implemented in [`freightvoice/security.py`](../freightvoice/security.py).

**Verify it:** `demo/simulate_call.py` posts **real Vapi-shaped payloads** to the
live webhooks (the same envelope Vapi sends), so the contract is exercised
end-to-end without a phone. `tests/test_webhooks.py` asserts the envelope shape.

**Honest scope:** the webhook path is the real production path. The *live phone
number* requires configuring the assistant in the Vapi dashboard (a Vapi
account) — that config lives in `VAPI_SETUP.md`, not in this repo.

---

## 2. Nebius — the LLM brain

**What it does:** runs the (fine-tunable) LLM that drives the conversation. Vapi
routes its model calls to **Nebius Token Factory** via Vapi's OpenAI-compatible
**custom-LLM (BYOK)** provider — so Nebius is the brain producing the structured
tool calls our webhooks receive.

**How we use it (config seam, by design):**
- Vapi model provider = `custom-llm`, base URL **`https://api.tokenfactory.nebius.com/v1/`**,
  with the Nebius API key set as the BYOK credential in Vapi's Provider Keys.
- **Model:** `Qwen/Qwen3-30B-A3B-Instruct-2507` — a Mixture-of-Experts model
  Nebius labels "optimized for tool use," with ~3B active params so it keeps
  voice-grade latency. Low-latency fallback:
  `meta-llama/Meta-Llama-3.1-8B-Instruct-fast` (the model in Nebius's own
  function-calling docs).
- Config block in [`VAPI_SETUP.md` §3](VAPI_SETUP.md); the `FreightVoice-FT-v1`
  supervised fine-tuning seam is documented in §4.

**Honest scope:** there is intentionally **no inference code in the middleware** —
a Vapi app receives already-structured tool arguments, so building inference in
would be wrong. Nebius is wired at Vapi's configuration layer, not called from
our Python. That's the correct architecture for a Vapi-fronted agent, and it's
why the core demo needs no Nebius key to run.

---

## 3. InsForge — the system of record

**What it does:** managed **Postgres + an auto-generated PostgREST-style REST
API** (plus pgvector). It backs the carrier TMS data — loads, PODs, and the
discrepancy queue — making the stand-in TMS run on a real database rather than a
toy.

**How we use it (live integration in code):**
- [`faketms/stores/insforge_store.py`](../faketms/stores/insforge_store.py) is a
  **real REST integration**: `GET/POST/PATCH/DELETE /api/database/records/{table}`,
  `Authorization: Bearer`, PostgREST `eq` filters. The "never downgrade a load's
  status" rule is enforced with a `PATCH …&status=eq.pending` filter.
- It sits behind a **storage seam** ([`faketms/stores/`](../faketms/stores/)) —
  same pattern as the TMS-adapter seam — so flipping one env var swaps SQLite for
  InsForge with zero service-layer changes.
- Exercised end-to-end in `tests/test_stores.py` against an in-memory PostgREST
  fake, including request-shaping assertions.

**Turn it on:**
```bash
export FAKETMS_STORAGE=insforge
export FAKETMS_INSFORGE_URL=http://localhost:7130        # or https://<app>.insforge.app
export FAKETMS_INSFORGE_TOKEN=your-insforge-bearer-token
```
Then create the three tables once in the InsForge project (DDL isn't part of the
records REST API — run it via an InsForge migration / the console):

```sql
create table loads (
  load_id text primary key,
  shipper text, consignee text, commodity text,
  expected_pieces int, expected_weight_lbs float8,
  scheduled_delivery text, equipment_type text,
  status text default 'pending', invoice_number text, delivered_at text
);
create table pods (
  id bigserial primary key,
  load_id text references loads(load_id),
  record_json text, readback text, clean boolean, created_at text
);
create table discrepancies (
  id bigserial primary key,
  load_id text references loads(load_id),
  code text, severity text, message text, transcript_excerpt text, created_at text
);
```

**Roadmap (documented, not in the demo):** the same InsForge project is the
**pgvector** store for the Batch B invoice-reconciliation layer — evidence chunks
filtered by relational keys (`load_id`, `source_type`) for RAG.

**Honest scope:** the core demo **defaults to SQLite** so it runs with zero
accounts (a judging requirement). InsForge is a real, tested integration that's
one env var away — the only setup is the three-table migration above.

---

## At a glance

| Sponsor | Layer | Integration type | Where in the repo | Lives in demo by default? |
|---|---|---|---|---|
| **Vapi** | Voice + tool orchestration | Live webhook contract | `freightvoice/vapi.py`, `app.py`, `docs/VAPI_SETUP.md` | Contract: yes (via `simulate_call.py`). Live call: Vapi dashboard config. |
| **Nebius** | LLM brain | Config seam via Vapi BYOK (by design) | `docs/VAPI_SETUP.md` §3–4 | Configured in Vapi, not called from our code. |
| **InsForge** | System of record (Postgres) | Live REST integration, env-switchable | `faketms/stores/insforge_store.py` | Opt-in (`FAKETMS_STORAGE=insforge`); SQLite default keeps demo account-free. |

The through-line: FreightVoice is built as a set of clean seams, and each sponsor
slots into one of them. That's what makes "the middleware is real; only the
carrier TMS is mocked" true — and what lets all three sponsors be genuine,
swappable parts of the same pipeline.
