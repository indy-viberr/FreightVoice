# Vapi Setup

This is the assistant configuration for FreightVoice. Point each tool `server.url` at your deployed HTTPS FreightVoice host, or at an ngrok URL during local testing.

## System Prompt

```text
You are FreightVoice, a logistics documentation assistant for truck drivers.
You help drivers complete post-delivery paperwork via a short phone call.

RULES - follow these exactly:
1. CONFIRM, DON'T DICTATE. Retrieve load details from the system, read them back, and ask the driver to confirm or correct.
2. USE CLOSED QUESTIONS for structured data.
3. READBACK BEFORE CLOSE. Read back every captured data point before ending the call.
4. GRACEFUL RETRY. Ask once more when you miss something. If you still cannot capture it, flag it for dispatch.
5. BREVITY FIRST. Complete the call in under 4 minutes.
6. NO JARGON. Say "did you drop the trailer" rather than "drop-and-hook."
7. SPANISH: If the driver speaks Spanish, switch fully to Spanish and stay there.

CALL FLOW:
1. Greet: "Hi, this is FreightVoice. What's your load number?"
2. Call get_load_context. Read back the load summary. Confirm.
3. Capture actual delivery time, recipient name, piece count, weight, and damage yes/no.
4. If damage: ask for description. Tell the driver to expect an SMS for photos.
5. Ask: "Any extra services - detention, liftgate, lumper?"
6. Capture each accessorial with duration or amount as needed.
7. Read back everything. Confirm. Call push_delivery_record.
8. Speak the push_delivery_record result verbatim.
9. Close: "You're all set. Drive safe."
```

## Tool Definitions

Register four Vapi function tools.

```json
{
  "type": "function",
  "function": {
    "name": "get_load_context",
    "description": "Retrieve load details by load_id or pro_number. Call this first and read the returned details back to the driver.",
    "parameters": {
      "type": "object",
      "properties": {
        "load_id": { "type": "string", "description": "Load ID as spoken by the driver." },
        "pro_number": { "type": "string", "description": "PRO number if load_id is not available." }
      },
      "required": []
    }
  },
  "server": { "url": "https://YOUR_URL/webhook/get_load_context" }
}
```

```json
{
  "type": "function",
  "function": {
    "name": "push_delivery_record",
    "description": "Submit the completed delivery record after reading back all captured data and receiving driver confirmation.",
    "parameters": {
      "type": "object",
      "properties": {
        "load_id": { "type": "string" },
        "delivered_at": { "type": "string", "description": "ISO 8601 UTC datetime" },
        "recipient_name": { "type": "string" },
        "actual_pieces": { "type": "integer" },
        "actual_weight_lbs": { "type": "number" },
        "damage": { "type": "boolean" },
        "damage_notes": { "type": "string" },
        "accessorials": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "type": {
                "type": "string",
                "enum": ["detention", "liftgate", "lumper", "residential", "inside_delivery", "layover", "tonu", "redelivery"]
              },
              "duration_minutes": { "type": "integer" },
              "amount_usd": { "type": "number" },
              "notes": { "type": "string" }
            },
            "required": ["type"]
          }
        },
        "exception_type": { "type": "string", "enum": ["refused", "short", "damage", "redelivery", "overage"] },
        "transcript_excerpt": { "type": "string" }
      },
      "required": ["load_id", "delivered_at", "recipient_name", "actual_pieces", "actual_weight_lbs", "damage"]
    }
  },
  "server": { "url": "https://YOUR_URL/webhook/push_delivery_record" }
}
```

```json
{
  "type": "function",
  "function": {
    "name": "flag_discrepancy",
    "description": "Escalate an ambiguous or unexpected driver report to dispatch.",
    "parameters": {
      "type": "object",
      "properties": {
        "load_id": { "type": "string" },
        "description": { "type": "string" },
        "transcript_excerpt": { "type": "string" }
      },
      "required": ["load_id", "description"]
    }
  },
  "server": { "url": "https://YOUR_URL/webhook/flag_discrepancy" }
}
```

```json
{
  "type": "function",
  "function": {
    "name": "schedule_callback",
    "description": "Record a callback request when the driver needs to hang up before documentation is complete.",
    "parameters": {
      "type": "object",
      "properties": {
        "load_id": { "type": "string" },
        "driver_phone": { "type": "string" },
        "reason": { "type": "string" }
      },
      "required": ["load_id"]
    }
  },
  "server": { "url": "https://YOUR_URL/webhook/schedule_callback" }
}
```

## Nebius BYOK Model Block

Use Vapi's custom LLM provider settings with your Nebius endpoint.

```json
{
  "provider": "custom-llm",
  "url": "https://api.studio.nebius.com/v1/",
  "model": "meta-llama/Llama-3.1-70B-Instruct-fast",
  "customLlmExtraParams": {
    "temperature": 0.3,
    "max_tokens": 512
  }
}
```

After fine-tuning, replace `model` with the endpoint ID returned by Nebius Token Factory. The middleware does not call Nebius directly; Vapi owns the speech and LLM runtime.

## STT

```json
{
  "provider": "deepgram",
  "model": "nova-3",
  "language": "en-US",
  "smartFormat": true
}
```

For Spanish, create a separate assistant with `language` set to `es` and a Spanish version of the system prompt.

