from __future__ import annotations

from fastapi import APIRouter, Query
from backend import db, schemas

router = APIRouter()

SORTS = {
    "aum_desc": "estimated_aum_usd DESC NULLS LAST",
    "aum_asc": "estimated_aum_usd ASC NULLS LAST",
    "name": "name ASC",
    "data_quality_desc": "data_quality DESC",
}

@router.get("/api/entities", response_model=schemas.EntitiesPage)
def list_entities(
    country: str | None = None,
    region: str | None = None,
    type: str | None = None,
    sector: str | None = None,
    min_aum_usd: float | None = None,
    max_aum_usd: float | None = None,
    controlling_family: str | None = None,
    q: str | None = None,
    sort: str = "aum_desc",
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    where: list[str] = []
    params: list = []
    if country:
        codes = [c.strip().upper() for c in country.split(",") if c.strip()]
        where.append(f"country IN ({','.join('?' * len(codes))})")
        params.extend(codes)
    if region:
        where.append("region = ?"); params.append(region)
    if type:
        types = [t.strip() for t in type.split(",") if t.strip()]
        where.append(f"type IN ({','.join('?' * len(types))})")
        params.extend(types)
    if sector:
        where.append("sectors LIKE ?"); params.append(f"%{sector}%")
    if min_aum_usd is not None:
        where.append("estimated_aum_usd >= ?"); params.append(min_aum_usd)
    if max_aum_usd is not None:
        where.append("estimated_aum_usd <= ?"); params.append(max_aum_usd)
    if controlling_family:
        where.append("controlling_family LIKE ?")
        params.append(f"%{controlling_family}%")
    if q:
        where.append("(name LIKE ? OR controlling_family LIKE ?)")
        params.extend([f"%{q}%", f"%{q}%"])

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    order_sql = SORTS.get(sort, SORTS["aum_desc"]).replace(" NULLS LAST", "")
    # SQLite doesn't support NULLS LAST; emulate via CASE.
    if "estimated_aum_usd" in order_sql:
        order_sql = (
            "CASE WHEN estimated_aum_usd IS NULL THEN 1 ELSE 0 END, "
            + order_sql
        )

    with db.get_conn() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM entities {where_sql}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM entities {where_sql} "
            f"ORDER BY {order_sql} LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()

    return {"total": total, "results": [dict(r) for r in rows]}
