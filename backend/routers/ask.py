from __future__ import annotations

import json
from fastapi import APIRouter, HTTPException
from backend import db, llm, schemas
from backend.routers.entities import list_entities

router = APIRouter()

SYSTEM = (
    "You map natural-language questions about Asian family-office capital pools "
    "to a single tool call: query_entities(filters). After the tool returns "
    "matches, write a 2-3 sentence factual answer and a list of cited_entity_ids. "
    "Reply with strict JSON: {\"answer\": str, \"cited_entity_ids\": [str]}."
)

TOOLS = [{
    "type": "function",
    "function": {
        "name": "query_entities",
        "description": "Filter the entities database. All filters AND-combined.",
        "parameters": {
            "type": "object",
            "properties": {
                "country": {"type": "string"},
                "region": {"type": "string"},
                "type": {"type": "string"},
                "sector": {"type": "string"},
                "min_aum_usd": {"type": "number"},
                "controlling_family": {"type": "string"},
                "q": {"type": "string"},
            },
        },
    },
}]

def _run_tool(args: dict) -> dict:
    page = list_entities(
        country=args.get("country"),
        region=args.get("region"),
        type=args.get("type"),
        sector=args.get("sector"),
        min_aum_usd=args.get("min_aum_usd"),
        controlling_family=args.get("controlling_family"),
        q=args.get("q"),
        sort="aum_desc", limit=50, offset=0,
    )
    return page

@router.post("/api/ask", response_model=schemas.AskResponse)
def ask(req: schemas.AskRequest):
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": req.question},
    ]
    first = llm.chat_completion(messages, tools=TOOLS)
    msg = first["choices"][0]["message"]
    tool_calls = msg.get("tool_calls") or []
    if not tool_calls:
        raise HTTPException(status_code=502, detail="LLM did not call tool")

    tc = tool_calls[0]
    args = json.loads(tc["function"]["arguments"])
    tool_result = _run_tool(args)

    messages.extend([
        {"role": "assistant", "content": None, "tool_calls": tool_calls},
        {"role": "tool", "tool_call_id": tc["id"],
         "content": json.dumps({"matches": [
             {"id": e["id"], "name": e["name"], "country": e["country"],
              "estimated_aum_usd": e["estimated_aum_usd"]}
             for e in tool_result["results"]
         ]})},
    ])

    second = llm.chat_completion(messages)
    text = second["choices"][0]["message"]["content"]
    parsed = json.loads(text)
    cited = set(parsed.get("cited_entity_ids", []))
    entities = [e for e in tool_result["results"] if e["id"] in cited]
    return {"answer": parsed.get("answer", ""), "entities": entities,
            "filters_used": args}
