"""
Vapi server-tool envelope helpers.

Vapi calls our webhooks as "server tools". The request wraps one or more tool
calls; the response must return a ``results`` array keyed by ``toolCallId``.

Documented shape (Vapi custom/server tools):
  https://docs.vapi.ai/tools/custom-tools
  https://docs.vapi.ai/server-url/events  (message.type == "tool-calls")

Request body (the fields we rely on):
  {
    "message": {
      "type": "tool-calls",
      "toolCalls": [                      # also seen as "toolCallList"
        {
          "id": "call_abc",
          "type": "function",
          "function": {
            "name": "get_load_context",
            "arguments": { ... }          # object, or a JSON-encoded string
          }
        }
      ]
    }
  }

Response body:
  { "results": [ { "toolCallId": "call_abc", "result": "<string>" } ] }

NOTE: Vapi has shipped slightly different envelopes across versions (toolCalls vs
toolCallList; arguments as object vs string). We normalize all of these. If your
Vapi account sends a shape this doesn't handle, check the doc URLs above rather
than guessing — the parser logs what it received.
"""

from __future__ import annotations

import json
from typing import Any


class ToolCall:
    __slots__ = ("id", "name", "arguments")

    def __init__(self, id: str, name: str | None, arguments: dict[str, Any]):
        self.id = id
        self.name = name
        self.arguments = arguments


def parse_tool_calls(body: dict[str, Any]) -> list[ToolCall]:
    """Extract tool calls from a Vapi envelope.

    Falls back to treating the whole body as a single bare-arguments call (id
    "direct") when there's no Vapi envelope — handy for curl/debugging and for
    tests that want to post args directly.
    """
    message = body.get("message") if isinstance(body, dict) else None
    raw_calls = None
    if isinstance(message, dict):
        raw_calls = message.get("toolCalls") or message.get("toolCallList")

    if not raw_calls:
        # Not a Vapi envelope — treat the body as direct arguments.
        return [ToolCall(id="direct", name=None, arguments=body if isinstance(body, dict) else {})]

    calls: list[ToolCall] = []
    for rc in raw_calls:
        fn = rc.get("function", {}) if isinstance(rc, dict) else {}
        args = fn.get("arguments", {})
        if isinstance(args, str):
            # Vapi sometimes sends arguments as a JSON-encoded string.
            try:
                args = json.loads(args) if args.strip() else {}
            except json.JSONDecodeError:
                args = {}
        calls.append(ToolCall(
            id=rc.get("id", "unknown"),
            name=fn.get("name"),
            arguments=args if isinstance(args, dict) else {},
        ))
    return calls


def results_envelope(results: list[tuple[str, Any]]) -> dict[str, Any]:
    """Build the response body from (toolCallId, result) pairs.

    ``result`` is coerced to a string: Vapi feeds it back to the LLM as the
    tool's return value, and the model speaks/acts on it. Structured payloads
    are JSON-stringified so the model can still parse them.
    """
    out = []
    for tool_call_id, result in results:
        if not isinstance(result, str):
            result = json.dumps(result)
        out.append({"toolCallId": tool_call_id, "result": result})
    return {"results": out}
