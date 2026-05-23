"""Tool-use orchestrator. Yields SSE event dicts."""
from __future__ import annotations
import asyncio
import json
from typing import AsyncIterator

from backend import llm
from backend.research import session, tools, prompts

MAX_TOOL_CALLS_PER_TURN = 8

async def run_turn(session_id: str, user_message: str
                   ) -> AsyncIterator[dict]:
    """Yields events: tool_call, tool_result, db_write, message, error, done."""
    session.append(session_id, {"role": "user", "content": user_message})
    messages: list[dict] = [
        {"role": "system", "content": prompts.SYSTEM_PROMPT},
        *session.history(session_id),
    ]
    calls_made = 0

    while True:
        if calls_made >= MAX_TOOL_CALLS_PER_TURN:
            yield {"event": "error",
                   "data": {"message": "tool-call cap reached"}}
            break

        # OpenRouter call (blocking) — run in thread to keep loop async
        try:
            resp = await asyncio.to_thread(
                llm.chat_completion, messages, tools.TOOL_SCHEMAS, "auto"
            )
        except Exception as e:
            yield {"event": "error", "data": {"message": str(e)}}
            break

        msg = resp["choices"][0]["message"]
        tool_calls = msg.get("tool_calls") or []

        if not tool_calls:
            text = msg.get("content") or ""
            session.append(session_id, {"role": "assistant", "content": text})
            yield {"event": "message", "data": {"text": text}}
            yield {"event": "done", "data": {}}
            break

        # Assistant turn with tool_calls (no content) — keep in message stream
        messages.append({"role": "assistant", "content": msg.get("content"),
                         "tool_calls": tool_calls})

        # Dispatch tools sequentially (most are stateful via DB / network)
        for tc in tool_calls:
            calls_made += 1
            name = tc["function"]["name"]
            args_str = tc["function"].get("arguments") or "{}"
            yield {"event": "tool_call",
                   "data": {"tool": name, "args": _safe_json(args_str)}}
            result_json = await asyncio.to_thread(tools.call, name, args_str)
            try:
                result_obj = json.loads(result_json)
            except json.JSONDecodeError:
                result_obj = {"raw": result_json[:200]}
            yield {"event": "tool_result",
                   "data": {"tool": name, "summary": _summarize(name, result_obj)}}
            if name == "commit_entity" and isinstance(result_obj, dict) \
               and result_obj.get("status") == "ok":
                yield {"event": "db_write",
                       "data": {"entity_id": result_obj.get("entity_id")}}
            messages.append({"role": "tool", "tool_call_id": tc["id"],
                             "content": result_json})

def _safe_json(s: str) -> dict:
    try:
        return json.loads(s)
    except Exception:
        return {"raw": s[:200]}

def _summarize(tool: str, obj: dict) -> str:
    if tool == "search_web":
        return f"{len(obj.get('hits') or [])} hits"
    if tool == "scrape_url":
        return f"{len(obj.get('markdown') or '')} chars"
    if tool == "query_db":
        return f"{obj.get('total', 0)} matches"
    if tool == "commit_entity":
        return f"{obj.get('status')}: {obj.get('entity_id') or obj.get('errors')}"
    if tool == "apollo_org_lookup":
        return "found" if obj.get("profile") else "no match"
    if tool == "finnhub_company":
        return "found" if obj.get("profile") else "no match"
    if tool == "polygon_ticker_lookup":
        return f"{len(obj.get('results') or [])} hits"
    return "ok"
