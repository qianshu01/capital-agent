"""In-memory chat session store. Ephemeral by design (matches no-cache spec)."""
from __future__ import annotations
import time

IDLE_TIMEOUT_SEC = 30 * 60

_SESSIONS: dict[str, dict] = {}  # sid -> {"messages": [...], "last_used": float}

def _now() -> float:  # patchable for tests
    return time.time()

def append(session_id: str, message: dict) -> None:
    s = _SESSIONS.setdefault(session_id, {"messages": [], "last_used": _now()})
    s["messages"].append(message)
    s["last_used"] = _now()

def history(session_id: str) -> list[dict]:
    s = _SESSIONS.get(session_id)
    return list(s["messages"]) if s else []

def prune() -> None:
    cutoff = _now() - IDLE_TIMEOUT_SEC
    dead = [sid for sid, s in _SESSIONS.items() if s["last_used"] < cutoff]
    for sid in dead:
        del _SESSIONS[sid]
