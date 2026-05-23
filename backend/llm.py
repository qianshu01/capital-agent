"""OpenRouter chat completion wrapper."""
from __future__ import annotations
import os
import httpx

URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.0-flash-exp:free")

def chat_completion(
    messages: list[dict],
    tools: list[dict] | None = None,
    tool_choice: str = "auto",
) -> dict:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    payload: dict = {"model": MODEL, "messages": messages}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice
    with httpx.Client(timeout=120.0) as c:
        r = c.post(URL,
                   headers={"Authorization": f"Bearer {key}",
                            "Content-Type": "application/json"},
                   json=payload)
        r.raise_for_status()
        return r.json()
