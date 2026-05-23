"""Exa neural search wrapper. EXA_API_KEY env."""
from __future__ import annotations
import os
import httpx

URL = "https://api.exa.ai/search"

def search(query: str, n: int = 5) -> list[dict]:
    """[{url, title, snippet}, ...]. [] when EXA_API_KEY missing or on error."""
    key = os.environ.get("EXA_API_KEY")
    if not key:
        return []
    try:
        with httpx.Client(timeout=30.0) as c:
            r = c.post(URL, headers={"x-api-key": key, "Content-Type": "application/json"},
                       json={"query": query, "numResults": min(n, 10),
                             "type": "neural", "contents": {"text": False}})
            if r.status_code != 200:
                print(f"[exa] {r.status_code}: {r.text[:200]}")
                return []
            data = r.json().get("results", [])
        return [{"url": x.get("url"), "title": x.get("title"),
                 "snippet": (x.get("text") or "")[:300]} for x in data][:n]
    except Exception as e:
        print(f"[exa] search failed: {e}")
        return []
