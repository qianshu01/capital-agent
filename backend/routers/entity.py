from fastapi import APIRouter, HTTPException
from backend import db, schemas

router = APIRouter()

@router.get("/api/entities/{entity_id}", response_model=schemas.EntityDetailV2)
def get_entity(entity_id: str):
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM entities WHERE id = ?", (entity_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="not found")
        sources = [dict(r) for r in conn.execute(
            "SELECT field, source_type, url, note, retrieved_at "
            "FROM sources WHERE entity_id = ?", (entity_id,)
        ).fetchall()]
        activities = [dict(r) for r in conn.execute(
            "SELECT date, kind, description, source_url "
            "FROM activities WHERE entity_id = ? ORDER BY date DESC",
            (entity_id,)
        ).fetchall()]
        assumptions = [r[0] for r in conn.execute(
            "SELECT text FROM assumptions WHERE entity_id = ?", (entity_id,)
        ).fetchall()]
        evidence_rows = conn.execute(
            "SELECT id, question_key, answer, confidence FROM evidence "
            "WHERE entity_id = ?", (entity_id,)
        ).fetchall()
        # Build evidence[].source_urls from sources.evidence_id back-references
        ev_id_to_urls: dict[int, list[str]] = {}
        for s in conn.execute(
            "SELECT evidence_id, url FROM sources "
            "WHERE entity_id = ? AND evidence_id IS NOT NULL",
            (entity_id,),
        ).fetchall():
            ev_id_to_urls.setdefault(s["evidence_id"], []).append(s["url"])
        evidence = [{
            "question_key": r["question_key"],
            "answer": r["answer"],
            "confidence": r["confidence"],
            "source_urls": ev_id_to_urls.get(r["id"], []),
        } for r in evidence_rows]

    return {"entity": dict(row), "sources": sources, "activities": activities,
            "assumptions": assumptions, "evidence": evidence}
