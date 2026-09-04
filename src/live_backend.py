"""The sole provider-specific boundary. Importing this module performs no I/O."""
from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

# One clear backend configuration area. The submitted/default path is free and local.
BACKEND = "scripted"
MODEL = "local-rule-planner"
BASE_URL = "https://openrouter.ai/api/v1/chat/completions"


@dataclass(frozen=True)
class LiveResponse:
    text: str
    usage: dict[str, Any]
    latency_seconds: float
    model: str | None = None
    response_id: str | None = None


class PaidMalformedResponse(RuntimeError):
    """HTTP-success response with billable evidence but unusable model content."""
    def __init__(self, message: str, *, usage: dict[str, Any], model: Any, response_id: Any,
                 latency_seconds: float) -> None:
        super().__init__(message)
        self.usage, self.model, self.response_id = usage, model, response_id
        self.latency_seconds = latency_seconds


def call_live_model(*, model: str, model_input: dict[str, Any], base_url: str = BASE_URL,
                    settings: dict[str, Any] | None = None,
                    transport: Callable[..., Any] = urllib.request.urlopen) -> LiveResponse:
    """Call the OpenRouter-compatible chat-completions endpoint; tests inject transport."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is required for live execution")
    body = json.dumps({"model": model, "messages": [
        {"role": "system", "content": model_input["system"]},
        {"role": "user", "content": json.dumps({k: v for k, v in model_input.items() if k != "system"},
                                                   sort_keys=True)},
    ], **(settings or {})}).encode()
    request = urllib.request.Request(base_url, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    started = time.monotonic()
    with transport(request, timeout=120) as response:
        raw = response.read().decode("utf-8")
    latency = time.monotonic() - started
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        raise PaidMalformedResponse("HTTP-success response was not valid JSON", usage={},
                                    model=None, response_id=None, latency_seconds=latency)
    payload_object = payload if isinstance(payload, dict) else {}
    usage = payload_object.get("usage")
    choices = payload_object.get("choices")
    first = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    message = first.get("message")
    text = message.get("content") if isinstance(message, dict) else None
    required_usage = ("prompt_tokens", "completion_tokens", "cost")
    usage_complete = isinstance(usage, dict) and all(
        isinstance(usage.get(key), (int, float)) and not isinstance(usage.get(key), bool) and
        usage[key] >= 0 for key in required_usage)
    if not isinstance(text, str) or not text.strip() or not usage_complete:
        raise PaidMalformedResponse("HTTP-success response had unusable content or usage",
                                    usage=dict(usage or {}) if isinstance(usage, dict) else {},
                                    model=payload_object.get("model"),
                                    response_id=payload_object.get("id"), latency_seconds=latency)
    return LiveResponse(text=text, usage=dict(usage),
                        latency_seconds=latency,
                        model=payload_object.get("model"), response_id=payload_object.get("id"))
