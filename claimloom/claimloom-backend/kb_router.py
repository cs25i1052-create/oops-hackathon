"""Truth Vault endpoints backed by public.kb_chunks."""
from typing import Optional

from fastapi import APIRouter, Body, HTTPException

import cache
import db
import pipeline
from seed_kb import KB_CHUNKS

router = APIRouter()


def _read_chunks():
    conn = db._connect()
    if not conn:
        return KB_CHUNKS
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT chunk_id,doc_title,page_num,paragraph_num,chunk_text,updated_at FROM public.kb_chunks ORDER BY chunk_id")
            rows = cur.fetchall()
        return [{"chunk_id": r[0], "doc_title": r[1], "page_num": r[2], "paragraph_num": r[3], "chunk_text": r[4], "updated_at": str(r[5]) if r[5] else None} for r in rows] or KB_CHUNKS
    except Exception:
        return KB_CHUNKS
    finally:
        conn.close()


@router.get("/api/kb/sources")
def get_sources(workspace_id: str = "default"):
    chunks = _read_chunks()
    sources = sorted({c["doc_title"] for c in chunks})
    return {"kb_version": pipeline.get_kb_version(workspace_id), "sources": sources, "chunks": chunks}


def _update_chunk(chunk_id: int, payload: dict):
    text = str(payload.get("chunk_text") or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="chunk_text is required")
    conn = db._connect()
    if not conn:
        raise HTTPException(status_code=503, detail="Knowledge Base database unavailable")
    try:
        with conn.cursor() as cur:
            title = payload.get("doc_title")
            cur.execute("UPDATE public.kb_chunks SET chunk_text=%s, doc_title=COALESCE(%s,doc_title), updated_at=CURRENT_TIMESTAMP WHERE chunk_id=%s", (text, title, chunk_id))
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Chunk not found")
            cur.execute("UPDATE public.kb_meta SET value=value+1 WHERE key='kb_version'")
        conn.commit()
    finally:
        conn.close()
    affected = pipeline.reaudit_changed([chunk_id])
    cache.invalidate_cache()
    return {"status": "updated", "chunk_id": chunk_id, "kb_version": pipeline.get_kb_version(), "affected_scans": affected, "affected_count": len(affected)}


@router.put("/api/kb/chunks/{chunk_id}")
def update_chunk(chunk_id: int, payload: dict = Body(...)):
    return _update_chunk(chunk_id, payload)


@router.put("/api/facts/{chunk_id}")
def update_fact(chunk_id: int, payload: dict = Body(...)):
    return _update_chunk(chunk_id, payload)


@router.post("/api/kb/sync")
def sync_kb():
    ids = [int(c["chunk_id"]) for c in _read_chunks()]
    affected = pipeline.reaudit_changed(ids)
    cache.invalidate_cache()
    return {"status": "synced", "kb_version": pipeline.get_kb_version(), "affected_scans": affected, "affected_count": len(affected)}


@router.post("/api/admin/reset-demo")
def reset_demo():
    from seed_db import FACTS_DATA, RULES_DATA
    from seed_kb import seed_kb
    conn = db._connect()
    if not conn:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM public.brand_rules")
            for r in RULES_DATA:
                cur.execute("INSERT INTO public.brand_rules (rule_id,violation_type,severity,rule_cited,source_ref,rule_text,regex_pattern,default_fix,claim_status,allowed_numbers,applies_to) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (rule_id) DO UPDATE SET rule_text=EXCLUDED.rule_text", tuple(r.get(k) for k in ("rule_id","violation_type","severity","rule_cited","source_ref","rule_text","regex_pattern","default_fix","claim_status","allowed_numbers","applies_to")))
            for f in FACTS_DATA:
                cur.execute("INSERT INTO public.facts (fact_id,fact_text,source_ref) VALUES (%s,%s,%s) ON CONFLICT (fact_id) DO UPDATE SET fact_text=EXCLUDED.fact_text,source_ref=EXCLUDED.source_ref", (f["fact_id"],f["fact_text"],f["source_ref"]))
            seed_kb(conn)
            cur.execute("UPDATE public.kb_meta SET value=1 WHERE key='kb_version'")
            cur.execute("DELETE FROM public.scan_cache")
        conn.commit()
    finally:
        conn.close()
    cache.invalidate_cache()
    return {"status": "reset", "rules_version": 1, "kb_version": 1}
