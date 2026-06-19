# Nebius Fine-Tune Plan

FreightVoice does not invoke Nebius directly. The fine-tuned model is a Vapi assistant runtime choice, not middleware code. This document records the training shape for a future `FreightVoice-FT-v1` model.

## Goal

Train a concise logistics call-control model that:

- asks closed questions,
- calls FreightVoice tools at the right time,
- reads webhook results verbatim,
- switches to Spanish when the driver does,
- escalates instead of looping when data is unclear.

## Training Data Shape

Use JSONL chat examples. Each line should contain a short phone-call turn sequence with tool-call intent and exact readback behavior.

```json
{"messages":[{"role":"system","content":"You are FreightVoice..."},{"role":"user","content":"Load FV-DEMO-001"},{"role":"assistant","content":"I'll pull that up now.","tool_calls":[{"name":"get_load_context","arguments":{"load_id":"FV-DEMO-001"}}]},{"role":"tool","name":"get_load_context","content":"Got it. Load FV-DEMO-001 - 24 pallets of dry goods..."},{"role":"assistant","content":"Got it. Load FV-DEMO-001 - 24 pallets of dry goods... Does that sound right?"}]}
```

Recommended buckets:

- 40% clean delivery captures
- 20% damage or shortage captures
- 15% accessorial captures
- 10% retry and correction turns
- 10% Spanish calls
- 5% explicit dispatcher escalation

## Reference SFT Script

This is intentionally documentation, not code invoked by the app.

```python
from __future__ import annotations

import os
from pathlib import Path

from openai import OpenAI


client = OpenAI(
    api_key=os.environ["NEBIUS_API_KEY"],
    base_url="https://api.studio.nebius.com/v1/",
)

training_file = client.files.create(
    file=Path("training/freightvoice_sft.jsonl").open("rb"),
    purpose="fine-tune",
)

job = client.fine_tuning.jobs.create(
    training_file=training_file.id,
    model="meta-llama/Llama-3.1-70B-Instruct-fast",
    suffix="FreightVoice-FT-v1",
    hyperparameters={
        "n_epochs": 3,
        "learning_rate_multiplier": 0.8,
    },
)

print(job.id)
```

## Evaluation Checklist

- Tool calls use the exact names in `docs/VAPI_SETUP.md`.
- The assistant never invents load context before `get_load_context`.
- The assistant always calls `push_delivery_record` after readback confirmation.
- The assistant speaks the tool result without summarizing away dispatcher warnings.
- Spanish examples keep the full conversation in Spanish.

