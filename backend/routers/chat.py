"""Chat endpoint with SSE-streamed tool-use events."""
from __future__ import annotations
import json
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from backend import schemas
from backend.research import loop, session

router = APIRouter()

@router.post("/api/chat")
async def chat(req: schemas.ChatRequest):
    async def event_stream():
        async for ev in loop.run_turn(req.session_id, req.message):
            yield {"event": ev["event"],
                   "data": json.dumps(ev.get("data") or {})}
    return EventSourceResponse(event_stream())

@router.get("/api/chat/{session_id}", response_model=schemas.ChatHistory)
def get_history(session_id: str):
    return {"session_id": session_id,
            "messages": [{"role": m.get("role"),
                          "content": m.get("content")}
                         for m in session.history(session_id)]}
