import json
from unittest.mock import patch

def _fake_openrouter_two_step(messages, tools=None):
    """First call: return a tool_call for query_entities. Second call: return final text."""
    # Look for an existing tool result in messages -> second turn
    if any(m.get("role") == "tool" for m in messages):
        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": json.dumps({
                        "answer": "Two Indian SFOs match.",
                        "cited_entity_ids": ["in-premji"],
                    }),
                }
            }]
        }
    return {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "c1", "type": "function",
                    "function": {"name": "query_entities",
                                 "arguments": json.dumps({"country": "IN", "type": "sfo"})}
                }]
            }
        }]
    }

def test_ask_calls_tool_then_returns_answer(client):
    with patch("backend.llm.chat_completion", side_effect=_fake_openrouter_two_step):
        r = client.post("/api/ask", json={"question": "Indian SFOs?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"].startswith("Two Indian")
    assert body["filters_used"] == {"country": "IN", "type": "sfo"}
    ids = {e["id"] for e in body["entities"]}
    assert "in-premji" in ids
