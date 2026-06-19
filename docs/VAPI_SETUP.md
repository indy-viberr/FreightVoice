# Vapi + Nebius setup (the LLM seam)

FreightVoice does **not** run inference. The voice agent's brain lives inside
Vapi's assistant config; FreightVoice only receives already-structured tool-call
arguments at its webhooks and returns spoken readbacks. This file is everything
you paste into Vapi to wire the call to the four webhooks in
[`freightvoice/app.py`](../freightvoice/app.py).

```
Driver dials ──► Vapi (ASR + LLM + TTS) ──► tool calls ──► FreightVoice webhooks
                        ▲                                         │
                        └──────────── spoken readback ◄───────────┘
```

Expose your local middleware to Vapi with a tunnel during the demo:

```bash
ngrok http 5000          # -> https://<sub>.ngrok.app  == $FV_BASE below
```

Set `FV_BASE` to that HTTPS origin everywhere `https://YOUR-FREIGHTVOICE-HOST`
appears below.

---

## 1. Assistant system prompt

Paste into the Vapi assistant's **System Prompt**. It encodes the PRD's
conversation-design principles: confirm-don't-dictate, closed questions,
explicit readback, graceful retry, brevity, no jargon.

```
You are the after-delivery check-in line for a freight carrier. A truck driver
calls you right after dropping a load. Your job: confirm what was delivered and
capture anything unusual, then let them go. You are calm, fast, and friendly —
the driver is tired and probably still in the cab.

CORE RULES
- Confirm, don't dictate. You already know the load details. Read them back and
  ask the driver to confirm — never make the driver recite what you already have.
  "I've got load L1001 for Kroger DC 42, twenty pieces of canned goods — does
  that sound right?"
- Ask closed questions. Prefer yes/no or single-number answers. "Did all twenty
  pieces make it off the truck?" not "How did the delivery go?"
- One question at a time. Never stack two asks in one breath.
- Read back before you commit. Before you submit the delivery, say the key facts
  back: pieces, who signed, any damage. Get a yes.
- Retry gracefully. If you mishear a load number, ask the driver to read it back
  one digit at a time. Never guess. Never invent a piece count or a name.
- Before every tool call, normalize the load or PRO number by uppercasing every
  letter while preserving digits and punctuation (for example, l10a-01 becomes
  L10A-01).
- Be brief. No filler, no jargon, no "per FMCSA regulation". Plain English.
- Don't re-ask what you already know. If the load context already has the
  consignee and commodity, don't ask the driver for them — just confirm.

FLOW
1. Greet, ask for the load or PRO number.
2. Call get_load_context with it. If not found, ask the driver to re-read it
   digit by digit and try again.
3. Read the load back. Confirm delivery happened.
4. Capture: piece count, who signed (recipient name), any damage, any extra
   services (detention/liftgate/lumper/etc.), and whether the load was refused
   or short.
5. Read back the key facts. On "yes", call push_delivery_record.
6. Speak the result string the webhook returns verbatim — it tells the driver
   whether it's billed or held for review.
7. If the driver reports something serious you can't fit into the record, call
   flag_discrepancy with a short transcript excerpt.
8. If the call drops or the driver has to go before finishing, call
   schedule_callback so we reach back out.

NEVER
- Never read back compliance/legal warnings to the driver.
- Never enter or repeat payment details.
- Never fabricate a recipient name, piece count, or weight. If unknown, leave it
  out and let the record flag it.
```

---

## 2. Tool definitions

Add these four as Vapi **server tools** (function tools with a `server.url`).
Vapi POSTs a `message.toolCalls[]` envelope and expects a `results[]` array keyed
by `toolCallId` — which is exactly what the webhooks return (see
[`freightvoice/vapi.py`](../freightvoice/vapi.py)). Doc:
https://docs.vapi.ai/tools/custom-tools

```json
{
  "type": "function",
  "function": {
    "name": "get_load_context",
    "description": "Look up a load by its load or PRO number so you can confirm details with the driver. Call this first.",
    "parameters": {
      "type": "object",
      "properties": {
        "load_id": { "type": "string", "description": "Load or PRO number as the driver read it." }
      },
      "required": ["load_id"]
    }
  },
  "server": { "url": "https://YOUR-FREIGHTVOICE-HOST/webhook/get_load_context" }
}
```

```json
{
  "type": "function",
  "function": {
    "name": "push_delivery_record",
    "description": "Submit the completed delivery after you've read the facts back and the driver confirmed. Returns a sentence to speak verbatim.",
    "parameters": {
      "type": "object",
      "properties": {
        "load_id":          { "type": "string" },
        "delivered_at":     { "type": "string", "description": "ISO 8601 timestamp of delivery." },
        "recipient_name":   { "type": "string", "description": "Who signed. Omit if the driver couldn't give a name." },
        "actual_pieces":    { "type": "integer", "minimum": 0 },
        "actual_weight_lbs":{ "type": "number",  "minimum": 0 },
        "damage":           { "type": "boolean" },
        "damage_notes":     { "type": "string" },
        "accessorials": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "type":            { "type": "string", "enum": ["detention","liftgate","lumper","residential","inside_delivery","layover","tonu"] },
              "duration_minutes":{ "type": "integer", "minimum": 0 },
              "amount_usd":      { "type": "number",  "minimum": 0 },
              "notes":           { "type": "string" }
            },
            "required": ["type"]
          }
        },
        "exception_type":     { "type": "string", "enum": ["refused","short","redelivery","damaged","overage"] },
        "transcript_excerpt": { "type": "string", "description": "Short verbatim quote if anything was unusual." }
      },
      "required": ["load_id", "delivered_at", "actual_pieces", "actual_weight_lbs"]
    }
  },
  "server": { "url": "https://YOUR-FREIGHTVOICE-HOST/webhook/push_delivery_record" }
}
```

```json
{
  "type": "function",
  "function": {
    "name": "flag_discrepancy",
    "description": "Escalate a problem to the carrier's review team with a short quote from the driver.",
    "parameters": {
      "type": "object",
      "properties": {
        "load_id":            { "type": "string" },
        "reason":             { "type": "string" },
        "severity":           { "type": "string", "enum": ["info","warning","critical"] },
        "transcript_excerpt": { "type": "string" }
      },
      "required": ["load_id", "reason"]
    }
  },
  "server": { "url": "https://YOUR-FREIGHTVOICE-HOST/webhook/flag_discrepancy" }
}
```

```json
{
  "type": "function",
  "function": {
    "name": "schedule_callback",
    "description": "Record that we should call the driver back (call dropped or they had to go).",
    "parameters": {
      "type": "object",
      "properties": {
        "load_id": { "type": "string" },
        "reason":  { "type": "string" },
        "phone":   { "type": "string" }
      },
      "required": ["reason"]
    }
  },
  "server": { "url": "https://YOUR-FREIGHTVOICE-HOST/webhook/schedule_callback" }
}
```

---

## 3. Custom LLM via Nebius (BYOK)

The PRD routes Vapi's LLM to a model hosted on **Nebius Token Factory** (formerly
Nebius AI Studio), using Vapi's OpenAI-compatible **custom LLM** provider. Vapi
calls Nebius' `/v1/chat/completions`; Nebius runs the model. (Confirm the exact
field names against Vapi's custom-LLM docs — https://docs.vapi.ai/customization/custom-llm —
rather than trusting this block verbatim; the provider schema has shifted across
Vapi versions.)

```json
{
  "model": {
    "provider": "custom-llm",
    "url": "https://api.tokenfactory.nebius.com/v1/",
    "model": "Qwen/Qwen3-30B-A3B-Instruct-2507",
    "temperature": 0.2,
    "metadata": { "comment": "MoE, tool-use optimized, low latency for voice. Swap -> FreightVoice-FT-v1 once SFT lands." }
  }
}
```

**Model choice:** `Qwen/Qwen3-30B-A3B-Instruct-2507` is a Mixture-of-Experts
model Nebius labels "optimized for tool use" with ~3B active params, so it keeps
voice-grade latency. Low-latency / lowest-cost fallback (and the model in
Nebius's own function-calling docs): `meta-llama/Meta-Llama-3.1-8B-Instruct-fast`.
Disable any "thinking" mode for voice — reasoning tokens are audible dead air.
Verify the exact model id in the Nebius console; native slugs are
HuggingFace-style and case-sensitive.

Set the Nebius API key as the BYOK credential for the custom-LLM provider in the
Vapi dashboard (Provider Keys). Nebius Token Factory docs:
https://docs.tokenfactory.nebius.com

Keep `temperature` low — this is a forms-over-voice task, not creative writing.

### Authenticating the webhooks (optional)

FreightVoice ships an opt-in verifier (off by default). To require authentication,
set on the middleware:

```bash
export VAPI_WEBHOOK_SECRET=your-secret
export VAPI_AUTH_MODE=token          # token (default) | hmac
```

Then configure Vapi to send it. In **token** mode, set the assistant/server
`secret` in the Vapi dashboard to the same value — Vapi sends it as the
`X-Vapi-Secret` header, which the middleware checks in constant time. In **hmac**
mode, FreightVoice expects an `X-Vapi-Signature` header equal to
`HMAC-SHA256(raw_body, secret)`.

> Vapi's exact header name and native HMAC support have shifted across versions —
> confirm against https://docs.vapi.ai/server-url#authentication and set
> `VAPI_SIGNATURE_HEADER` / `VAPI_AUTH_MODE` to match what your account sends.
> Unauthenticated calls get `401 {"error":"unauthorized"}`.

---

## 4. Fine-tuning seam — `FreightVoice-FT-v1` (documented, NOT run)

The production plan is to SFT a small Llama on real (anonymized) check-in
transcripts so the agent nails freight phrasing, accessorial names, and the
confirm-don't-dictate cadence with fewer tokens. This is a **future seam** — the
demo runs fine on the base instruct model. The script below is included for
reference and is intentionally not invoked anywhere in the codebase.

```python
# scripts/sft_freightvoice_ft_v1.py  —  REFERENCE ONLY, not wired into the demo.
# Supervised fine-tune of a base Llama on FreightVoice check-in transcripts,
# run on Nebius Token Factory's fine-tuning API. Pseudocode-level; fill in the
# dataset of {messages:[...]} chat samples drawn from real calls.
#
#   data/freightvoice_sft.jsonl  — one chat sample per line:
#     {"messages":[{"role":"system","content":"<the system prompt above>"},
#                  {"role":"user","content":"<driver turn>"},
#                  {"role":"assistant","content":"<ideal agent turn / tool call>"}]}

import os
from openai import OpenAI  # Nebius exposes an OpenAI-compatible client

client = OpenAI(
    base_url="https://api.tokenfactory.nebius.com/v1/",
    api_key=os.environ["NEBIUS_API_KEY"],
)

def main():
    training_file = client.files.create(
        file=open("data/freightvoice_sft.jsonl", "rb"),
        purpose="fine-tune",
    )
    job = client.fine_tuning.jobs.create(
        training_file=training_file.id,
        model="meta-llama/Meta-Llama-3.1-8B-Instruct",
        suffix="FreightVoice-FT-v1",
        hyperparameters={"n_epochs": 3},
    )
    print("submitted fine-tune job:", job.id)
    # On completion, set model.model in the Vapi custom-LLM block (section 3)
    # to the resulting fine-tuned model id.

if __name__ == "__main__":
    main()
```
