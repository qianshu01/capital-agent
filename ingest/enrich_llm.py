"""Optional LLM enrichment via OpenRouter. Skipped when OPENROUTER_API_KEY is unset
or the run was invoked without --enrich."""
from __future__ import annotations

import json
import os
import httpx

URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.environ.get("OPENROUTER_MODEL", "owl-alpha")

PROMPT = (
    "Given this entity JSON, return a strict JSON object with keys "
    "thesis_blurb (1–2 sentences, factual, no marketing language), "
    "deployment (one of: direct, external_managers, mixed, unknown), "
    "accessibility (one of: open, restricted, closed, unknown). "
    "If you do not have evidence, set deployment/accessibility to 'unknown'. "
    "Return ONLY the JSON object."
)

def enrich(entity: dict) -> dict:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return {}
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                URL,
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"},
                json={
                    "model": MODEL,
                    "messages": [
                        {"role": "system", "content": PROMPT},
                        {"role": "user", "content": json.dumps(entity)},
                    ],
                    "response_format": {"type": "json_object"},
                },
            )
            if r.status_code != 200:
                print(f"[enrich] {r.status_code}: {r.text[:200]}")
                return {}
            content = r.json()["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as e:
        print(f"[enrich] failed for {entity.get('id')}: {e}")
        return {}
