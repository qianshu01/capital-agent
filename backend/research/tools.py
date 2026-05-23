"""Tool functions exposed to the LLM, with JSON schemas."""
from __future__ import annotations
import json
from backend import db as backend_db
from backend.routers.entities import list_entities as _list_entities
from ingest.sources import exa, firecrawl, apollo, finnhub, polygon

# ---- Tool implementations ----------------------------------------------------

def search_web(query: str, n: int = 5) -> dict:
    return {"hits": exa.search(query, n=n)}

def scrape_url(url: str) -> dict:
    return {"url": url, "markdown": firecrawl.scrape(url) or ""}

def apollo_org_lookup(name: str) -> dict:
    return {"name": name, "profile": apollo.org_lookup(name)}

def finnhub_company(ticker: str) -> dict:
    return {"ticker": ticker, "profile": finnhub.company(ticker)}

def polygon_ticker_lookup(query: str, n: int = 5) -> dict:
    return {"query": query, "results": polygon.ticker_lookup(query, n=n)}

def query_db(filters: dict | None = None) -> dict:
    filters = filters or {}
    page = _list_entities(
        country=filters.get("country"),
        region=filters.get("region"),
        type=filters.get("type"),
        sector=filters.get("sector"),
        min_aum_usd=filters.get("min_aum_usd"),
        max_aum_usd=filters.get("max_aum_usd"),
        controlling_family=filters.get("controlling_family"),
        q=filters.get("q"),
        sort=filters.get("sort", "aum_desc"),
        limit=min(int(filters.get("limit", 20)), 50),
        offset=int(filters.get("offset", 0)),
    )
    # Trim entity rows to keep the LLM context small
    return {
        "total": page["total"],
        "results": [
            {"id": r["id"], "name": r["name"], "country": r["country"],
             "type": r["type"], "estimated_aum_usd": r["estimated_aum_usd"]}
            for r in page["results"][:20]
        ],
    }

def commit_entity(bundle: dict) -> dict:
    return backend_db.commit_evidence_bundle(bundle)

# ---- Dispatch table ----------------------------------------------------------

TOOL_FUNCS = {
    "search_web": search_web,
    "scrape_url": scrape_url,
    "apollo_org_lookup": apollo_org_lookup,
    "finnhub_company": finnhub_company,
    "polygon_ticker_lookup": polygon_ticker_lookup,
    "query_db": query_db,
    "commit_entity": commit_entity,
}

def call(name: str, arguments_json: str) -> str:
    """Dispatch a tool call; return JSON string for the LLM tool message."""
    fn = TOOL_FUNCS.get(name)
    if fn is None:
        return json.dumps({"error": f"unknown tool: {name}"})
    try:
        args = json.loads(arguments_json or "{}")
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"bad JSON arguments: {e}"})
    try:
        return json.dumps(fn(**args))
    except TypeError as e:
        return json.dumps({"error": f"argument error: {e}"})
    except Exception as e:
        # Surface the error to the LLM so it can retry with a corrected call,
        # rather than crashing the whole run_turn coroutine.
        return json.dumps({"error": f"{type(e).__name__}: {e}"})

# ---- JSON schemas for OpenRouter tool-calling --------------------------------

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "search_web",
        "description": "Neural web search via Exa. Use to discover candidate vehicles or news.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "n": {"type": "integer", "default": 5}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "scrape_url",
        "description": "Fetch a URL via Firecrawl, returns markdown (≤8000 chars). Use to read primary sources.",
        "parameters": {"type": "object", "properties": {
            "url": {"type": "string"}}, "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "apollo_org_lookup",
        "description": "Look up an organization in Apollo (website, hq, employees, founded, industry).",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "finnhub_company",
        "description": "Get fundamentals for a listed ticker from Finnhub.",
        "parameters": {"type": "object", "properties": {
            "ticker": {"type": "string"}}, "required": ["ticker"]}}},
    {"type": "function", "function": {
        "name": "polygon_ticker_lookup",
        "description": "Resolve a name to a ticker via Polygon.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "n": {"type": "integer", "default": 5}}, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "query_db",
        "description": "Search the local Capital Agent DB to avoid duplicating work.",
        "parameters": {"type": "object", "properties": {
            "filters": {"type": "object"}}}}},
    {"type": "function", "function": {
        "name": "commit_entity",
        "description": (
            "Persist a fully evidenced investment-vehicle bundle to the DB. "
            "Must include `entity`, `evidence` (≥5 of the 7 questions, each citing URLs "
            "present in `sources`), and `sources`. Server validates and may reject."),
        "parameters": {"type": "object", "properties": {
            "bundle": {"type": "object"}}, "required": ["bundle"]}}},
]
