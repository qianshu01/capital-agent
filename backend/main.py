from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from backend.routers import entities, entity, ask

app = FastAPI(title="Capital Agent")
app.include_router(entities.router)
app.include_router(entity.router)
app.include_router(ask.router)

STATIC = Path(__file__).parent / "static"
if STATIC.exists():
    app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
