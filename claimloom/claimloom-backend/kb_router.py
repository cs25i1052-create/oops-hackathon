"""Truth Vault endpoints backed by public.kb_chunks."""
import json
from typing import Optional

from fastapi import APIRouter, Body, HTTPException

import cache
import db
import pipeline
from seed_kb import KB_CHUNKS

router = APIRouter()


def _read_chunks(workspace_id: str = "default"):
    workspace = (workspace_id or "default").strip() or "default"
    conn = db._connect()
    if not conn:
        return KB_CHUNKS
    try:
        with conn.cursor() as cur:
            if workspace == "default":
                cur.execute("SELECT chunk_id,doc_title,page_num,paragraph_num,chunk_text,updated_at FROM public.kb_chunks WHERE workspace_id=%s ORDER BY chunk_id", (workspace,))
            else:
                cur.execute("SELECT chunk_id,doc_title,page_num,paragraph_num,chunk_text,updated_at FROM public.kb_chunks WHERE workspace_id IN ('default', %s) ORDER BY chunk_id", (workspace,))
            rows = cur.fetchall()
        return [{"chunk_id": r[0], "doc_title": r[1], "page_num": r[2], "paragraph_num": r[3], "chunk_text": r[4], "updated_at": str(r[5]) if r[5] else None} for r in rows] or KB_CHUNKS
    except Exception:
        return KB_CHUNKS
    finally:
        conn.close()


@router.get("/api/kb/sources")
def get_sources(workspace_id: str = "default"):
    chunks = _read_chunks(workspace_id)
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
    import rules_router
    import rag_verifier
    import main
    import pdf_engine

    demo_scans = [
        ("demo_scan_1", "Our new Pro Plan is amazing at just $29/month!"),
        ("demo_scan_2", "Sign up today for $29/month to get the Pro Plan features."),
    ]
    demo_evidence = []
    for scan_id, text in demo_scans:
        evidence = {
            "verdict": "Verified",
            "doc_title": "Approved Pricing Sheet Q4",
            "page": 1,
            "paragraph": 1,
            "excerpt": "ClaimLoom Pro Plan subscription price is $29/month or $290/year.",
            "similarity": 0.95,
            "chunk_id": 3,
        }
        payload = {
            "scan_id": scan_id,
            "readiness_score": 100,
            "status": "approved",
            "ai_status": "ok",
            "pillar_scores": {"tone": 100, "terminology": 100, "claims": 100, "accessibility": 100, "visual": 100},
            "ai_disclosure": "Pre-approved ClaimLoom demo scan.",
            "pii_redacted_count": 0,
            "issues": [],
            "input_type": "text",
            "redacted_text": text,
            "cached": False,
            "channel": "general",
            "workspace_id": "default",
            "kb_version": 1,
            "rules_version": 1,
            "page_count": 1,
            "verified_claims": [evidence],
            "reaudit": {"needed": False, "note": None},
        }
        main._mem_scans[scan_id] = payload
        pdf_engine._mem_scan_json[scan_id] = payload
        demo_evidence.append({"scan_id": scan_id, "claim_text": text, "chunk_id": 3, "verdict": "Verified", "similarity": 0.95})
    rag_verifier._mem_evidence[:] = [row for row in rag_verifier._mem_evidence if not str(row.get("scan_id", "")).startswith("demo_scan_")]
    rag_verifier._mem_evidence.extend(demo_evidence)

    conn = db._connect()
    if conn:
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
                for scan_id, text in demo_scans:
                    payload = main._mem_scans[scan_id]
                    cur.execute(
                        """INSERT INTO public.scan_documents
                           (scan_id, workspace_id, channel, redacted_text, result_json, reaudit_needed, reaudit_reason)
                           VALUES (%s, 'default', 'general', %s, %s::jsonb, FALSE, NULL)
                           ON CONFLICT (scan_id) DO UPDATE SET redacted_text=EXCLUDED.redacted_text,
                           result_json=EXCLUDED.result_json, reaudit_needed=FALSE, reaudit_reason=NULL""",
                        (scan_id, text, json.dumps(payload)),
                    )
                    cur.execute("DELETE FROM public.claim_evidence WHERE scan_id=%s", (scan_id,))
                    cur.execute(
                        """INSERT INTO public.claim_evidence (scan_id, claim_text, chunk_id, verdict, similarity)
                           VALUES (%s, %s, 3, 'Verified', 0.95)""",
                        (scan_id, text),
                    )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise HTTPException(status_code=503, detail=f"Could not reset demo data: {exc}") from exc
        finally:
            conn.close()

    db._cache["at"] = 0
    db.get_vault(force=True)
    rules_router._memory_history.clear()
    rules_router._history_loaded.clear()
    cache.invalidate_cache()
    return {"status": "reset", "rules_version": 1, "kb_version": 1}
