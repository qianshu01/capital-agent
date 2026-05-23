"""Chat completion wrapper. Uses OpenAI direct if OPENAI_API_KEY is set,
otherwise falls back to OpenRouter."""
from __future__ import annotations
import os
import httpx

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _provider() -> tuple[str, str, str]:
    """Return (url, api_key, model)."""
    openai_key = os.environ.get("OPENAI_API_KEY")
    if openai_key:
        model = os.environ.get("OPENAI_MODEL", "gpt-4o")
        return OPENAI_URL, openai_key, model
    or_key = os.environ.get("OPENROUTER_API_KEY")
    if or_key:
        model = os.environ.get(
            "OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"
        )
        return OPENROUTER_URL, or_key, model
    raise RuntimeError("Set OPENAI_API_KEY or OPENROUTER_API_KEY")


def chat_completion(
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: str = "auto",
) -> dict:
    url, key, model = _provider()
    payload: dict = {"model": model, "messages": messages}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice
    with httpx.Client(timeout=120.0) as c:
        r = c.post(
            url,
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json=payload,
        )
        r.raise_for_status()
        return r.json()
