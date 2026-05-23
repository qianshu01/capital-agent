# tests/backend/test_session.py
import time
from backend.research import session as S

def test_history_starts_empty():
    sid = "test-1"
    assert S.history(sid) == []

def test_append_and_history():
    sid = "test-2"
    S.append(sid, {"role": "user", "content": "hi"})
    S.append(sid, {"role": "assistant", "content": "hello"})
    assert S.history(sid) == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]

def test_prune_evicts_idle(monkeypatch):
    sid = "test-3"
    S.append(sid, {"role": "user", "content": "x"})
    # fake time 31 min later
    monkeypatch.setattr(S, "_now", lambda: time.time() + 31 * 60)
    S.prune()
    assert S.history(sid) == []
