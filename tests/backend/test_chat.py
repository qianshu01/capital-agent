# tests/backend/test_chat.py
import importlib
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from ingest.write_db import build_db
from ingest.migrate_evidence import migrate

@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    db = tmp_path / "t.db"
    build_db(db, [], [], [], [])
    migrate(db)
    monkeypatch.setenv("DB_PATH", str(db))
    monkeypatch.setenv("OPENROUTER_API_KEY", "fake")
    import backend.db, backend.research.session
    importlib.reload(backend.db)
    backend.research.session._SESSIONS.clear()
    from backend.main import app
    return TestClient(app, raise_server_exceptions=False)

def _llm_responses():
    """Two-turn LLM: first turn calls search_web, second turn returns final text."""
    state = {"turn": 0}
    def fake(messages, tools=None, tool_choice="auto"):
        state["turn"] += 1
        if state["turn"] == 1:
            return {"choices": [{"message": {
                "role": "assistant", "content": None,
                "tool_calls": [{
                    "id": "c1", "type": "function",
                    "function": {"name": "search_web",
                                 "arguments": json.dumps({"query": "test"})}
                }]
            }}]}
        return {"choices": [{"message": {
            "role": "assistant",
            "content": "Done — no candidates found.",
            "tool_calls": None,
        }}]}
    return fake

def test_chat_streams_tool_call_and_message(client):
    with patch("backend.llm.chat_completion", side_effect=_llm_responses()):
        with client.stream("POST", "/api/chat",
                           json={"session_id": "s1", "message": "hi"}) as r:
            assert r.status_code == 200
            events = []
            for line in r.iter_lines():
                if line.startswith("event:"):
                    events.append(line.split(":", 1)[1].strip())
            assert "tool_call" in events
            assert "message" in events
            assert "done" in events

def test_chat_history_endpoint(client):
    with patch("backend.llm.chat_completion", side_effect=_llm_responses()):
        with client.stream("POST", "/api/chat",
                           json={"session_id": "s2", "message": "hello"}) as r:
            for _ in r.iter_lines():
                pass  # drain
    r2 = client.get("/api/chat/s2")
    assert r2.status_code == 200
    body = r2.json()
    assert body["session_id"] == "s2"
    assert any(m["role"] == "user" for m in body["messages"])
