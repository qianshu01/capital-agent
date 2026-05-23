"""Pydantic response models."""
from __future__ import annotations

import json
from typing import Any
from pydantic import BaseModel, field_validator

class Entity(BaseModel):
    id: str
    name: str
    type: str
    country: str
    region: str
    controlling_family: str | None = None
    controllers: list[str] | None = None
    ticker: str | None = None
    exchange: str | None = None
    estimated_aum_usd: float | None = None
    aum_basis: str | None = None
    ownership_pct: float | None = None
    sectors: list[str] | None = None
    deployment: str | None = None
    accessibility: str | None = None
    thesis_blurb: str | None = None
    data_quality: int
    updated_at: str

    @field_validator("controllers", "sectors", mode="before")
    @classmethod
    def _parse_json(cls, v: Any):
        if isinstance(v, str):
            return json.loads(v)
        return v

class EntitiesPage(BaseModel):
    total: int
    results: list[Entity]

class Source(BaseModel):
    field: str
    source_type: str
    url: str | None = None
    note: str | None = None
    retrieved_at: str

class Activity(BaseModel):
    date: str | None = None
    kind: str
    description: str
    source_url: str | None = None

class EntityDetail(BaseModel):
    entity: Entity
    sources: list[Source]
    activities: list[Activity]
    assumptions: list[str]

class AskRequest(BaseModel):
    question: str

class AskResponse(BaseModel):
    answer: str
    entities: list[Entity]
    filters_used: dict

class Evidence(BaseModel):
    question_key: str
    answer: str
    confidence: int
    source_urls: list[str] = []

class EntityDetailV2(BaseModel):
    """Detail response including evidence. Replaces EntityDetail at the API layer."""
    entity: Entity
    sources: list[Source]
    activities: list[Activity]
    assumptions: list[str]
    evidence: list[Evidence]

class ChatRequest(BaseModel):
    session_id: str
    message: str

class ChatHistoryMessage(BaseModel):
    role: str
    content: str | None = None

class ChatHistory(BaseModel):
    session_id: str
    messages: list[ChatHistoryMessage]
