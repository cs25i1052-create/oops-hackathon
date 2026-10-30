"""Truth Vault endpoints backed by public.kb_chunks."""
import json
import re
from typing import Optional

from fastapi import APIRouter, Body, HTTPException

import cache
import db
import pipeline
import rule_version
import seed_kb
from seed_kb import KB_CHUNKS

router = APIRouter()

_PRICE_RE = re.compile(r"\$\s*(\d+(?:\.\d{1,2})?)\s*(?:/|per\s+)?(?:month|mo)\b", re.I)


def _safe_connect():
    try:
        return db._connect()
    except Exception:
        return None


def _read_chunks(workspace_id: str = "default"):
    workspace = (workspace_id or "default").strip() or "default"
    conn = _safe_connect()
    if not conn:
        return KB_CHUNKS
    try:
        with conn.cursor() as cur:
            try:
                cur.execute("ALTER TABLE public.kb_chunks ADD COLUMN IF NOT EXISTS doc_title TEXT;")
                cur.execute("ALTER TABLE public.kb_chunks ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(64) DEFAULT 'default';")
                cur.execute("ALTER TABLE public.kb_chunks ADD COLUMN IF NOT EXISTS page_num INT DEFAULT 1;")
                cur.execute("ALTER TABLE public.kb_chunks ADD COLUMN IF NOT EXISTS paragraph_num INT DEFAULT 1;")
                conn.commit()
            except Exception:
                conn.rollback()

            if workspace == "default":
                cur.execute("SELECT chunk_id,doc_title,page_num,paragraph_num,chunk_text,updated_at FROM public.kb_chunks WHERE workspace_id=%s ORDER BY chunk_id", (workspace,))
            else:
                cur.execute("SELECT chunk_id,doc_title,page_num,paragraph_num,chunk_text,updated_at FROM public.kb_chunks WHERE workspace_id IN ('default', %s) ORDER BY chunk_id", (workspace,))
            rows = cur.fetchall()
        return [{"chunk_id": r[0], "doc_title": r[1] or f"Spec #{r[0]}", "page_num": r[2] or 1, "paragraph_num": r[3] or 1, "chunk_text": r[4], "updated_at": str(r[5]) if r[5] else None} for r in rows] or KB_CHUNKS
    except Exception:
        return KB_CHUNKS
    finally:
        try:
            conn.close()
        except Exception:
            pass


@router.get("/api/kb/sources")
@router.get("/api/kb/chunks")
def get_kb_sources(workspace_id: str = "default"):
    """Return truth vault knowledge chunks and active KB version."""
    chunks = _read_chunks(workspace_id)
    kb_ver = pipeline.get_kb_version(workspace_id)
    return {"chunks": chunks, "kb_version": kb_ver}


def ensure_demo_scans_seeded():
    """Seed demo_scan_1 and demo_scan_2 into memory stores if they are missing.

    Called at lifespan startup and at the start of _update_chunk() for chunk 3
    so that clicking "Demo Price Change & Sync" on a fresh server always
    returns affected_count >= 2.
    """
    import main
    import pdf_engine
    import rag_verifier

    demo_scans = [
        ("demo_scan_1", "Our new Pro Plan is amazing at just $29/month!"),
        ("demo_scan_2", "Sign up today for $29/month to get the Pro Plan features."),
    ]

    for scan_id, text in demo_scans:
        if scan_id not in main._mem_scans:
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

    # Ensure evidence rows exist for chunk 3 for both demo scans
    existing_ids = {str(row.get("scan_id")) for row in rag_verifier._mem_evidence}
    for scan_id, text in demo_scans:
        if scan_id not in existing_ids:
            rag_verifier._mem_evidence.append({
                "scan_id": scan_id,
                "claim_text": text,
                "chunk_id": 3,
                "verdict": "Verified",
                "similarity": 0.95,
            })

    # Also persist to Neon if connected and demo_scan_1 not already there
    conn = _safe_connect()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM public.scan_documents WHERE scan_id='demo_scan_1' LIMIT 1")
                already = cur.fetchone()
                if not already:
                    import main as _main
                    for scan_id, text in demo_scans:
                        payload = _main._mem_scans.get(scan_id, {})
                        cur.execute(
                            """INSERT INTO public.scan_documents
                               (scan_id, workspace_id, channel, redacted_text, result_json, reaudit_needed, reaudit_reason)
                               VALUES (%s, 'default', 'general', %s, %s::jsonb, FALSE, NULL)
                               ON CONFLICT (scan_id) DO NOTHING""",
                            (scan_id, text, json.dumps(payload)),
                        )
                        cur.execute(
                            """INSERT INTO public.claim_evidence (scan_id, claim_text, chunk_id, verdict, similarity)
                               VALUES (%s, %s, 3, 'Verified', 0.95)
                               ON CONFLICT DO NOTHING""",
                            (scan_id, text),
                        )
            conn.commit()
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"[kb_router] ensure_demo_scans_seeded DB write skipped: {exc}")
        finally:
            conn.close()


def _update_rule5_for_price(new_price: str):
    """Update Rule #5 in db._cache and optionally Neon for a new Pro Plan monthly price."""
    new_price = new_price.strip()
    for rule in db._cache.get("rules", []):
        if rule.get("rule_id") == 5:
            rule["allowed_numbers"] = new_price
            rule["default_fix"] = f"${new_price}/month"
            rule["rule_cited"] = f"Brand Rule 5: Pro Plan pricing is ${new_price}/month"
            rule["rule_text"] = f"The ClaimLoom Pro Plan costs ${new_price}/month (or ${int(float(new_price)) * 10}/year). Any other Pro price is outdated."
            break

    conn = _safe_connect()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE public.brand_rules
                       SET allowed_numbers=%s, default_fix=%s, rule_cited=%s, rule_text=%s
                       WHERE rule_id=5""",
                    (
                        new_price,
                        f"${new_price}/month",
                        f"Brand Rule 5: Pro Plan pricing is ${new_price}/month",
                        f"The ClaimLoom Pro Plan costs ${new_price}/month (or ${int(float(new_price)) * 10}/year). Any other Pro price is outdated.",
                    ),
                )
                cur.execute(
                    "UPDATE public.facts SET fact_text=%s WHERE fact_id=103",
                    (f"ClaimLoom Pro Plan subscription price is ${new_price}/month or ${int(float(new_price)) * 10}/year.",),
                )
            conn.commit()
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"[kb_router] Rule #5 Neon update skipped: {exc}")
        finally:
            conn.close()

    rule_version.set_rules_version(rule_version.get_rules_version() + 1)


def _update_chunk(chunk_id: int, payload: dict):
    text = str(payload.get("chunk_text") or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="chunk_text is required")

    # Fix 1: Seed demo scans if updating chunk 3 and evidence rows are missing
    if chunk_id == 3:
        import rag_verifier
        has_chunk3_evidence = any(
            row.get("chunk_id") == 3
            for row in rag_verifier._mem_evidence
        )
        if not has_chunk3_evidence:
            try:
                ensure_demo_scans_seeded()
            except Exception as exc:
                print(f"[kb_router] ensure_demo_scans_seeded failed: {exc}")

    conn = _safe_connect()
    if conn:
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
    else:
        found = False
        for kc in seed_kb.KB_CHUNKS:
            if kc["chunk_id"] == chunk_id:
                kc["chunk_text"] = text
                if payload.get("doc_title"):
                    kc["doc_title"] = payload["doc_title"]
                found = True
                break
        if not found:
            raise HTTPException(status_code=404, detail="Chunk not found")

    # Fix 1: Detect Pro Plan price change and update Rule #5
    doc_title = str(payload.get("doc_title") or "")
    is_pricing_chunk = (chunk_id == 3) or "pricing" in doc_title.lower() or "price" in doc_title.lower()
    if is_pricing_chunk:
        price_match = _PRICE_RE.search(text)
        if price_match:
            new_price = price_match.group(1).rstrip(".")
            try:
                _update_rule5_for_price(new_price)
                # Also update seed_kb.KB_CHUNKS in-memory for offline fallback
                for kc in seed_kb.KB_CHUNKS:
                    if kc["chunk_id"] == chunk_id:
                        kc["chunk_text"] = text
                        break
                # Force cache refresh so new rules take effect immediately
                db._cache["at"] = 0
            except Exception as exc:
                print(f"[kb_router] price sync update failed: {exc}")

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
    from seed_kb import seed_kb as _seed_kb
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

    # Restore Rule #5 to $29/month in-memory cache
    for rule in db._cache.get("rules", []):
        if rule.get("rule_id") == 5:
            rule["allowed_numbers"] = "29"
            rule["default_fix"] = "$29/month"
            rule["rule_cited"] = "Brand Rule 5: Pro Plan pricing is $29/month"
            rule["rule_text"] = "The ClaimLoom Pro Plan costs $29/month (or $290/year). Any other Pro price is outdated."
            break

    # Restore KB_CHUNKS chunk #3 in memory
    for kc in seed_kb.KB_CHUNKS:
        if kc["chunk_id"] == 3:
            kc["chunk_text"] = "ClaimLoom Pro Plan subscription price is $29/month or $290/year."
            break

    conn = _safe_connect()
    if conn:
        try:
            with conn.cursor() as cur:
                # Self-healing schema migrations for legacy tables
                cur.execute("CREATE TABLE IF NOT EXISTS public.kb_meta (key TEXT PRIMARY KEY, value INT NOT NULL DEFAULT 1);")
                cur.execute("INSERT INTO public.kb_meta (key, value) VALUES ('kb_version', 1) ON CONFLICT (key) DO NOTHING;")
                cur.execute("ALTER TABLE public.brand_rules ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(64) DEFAULT 'default';")
                cur.execute("ALTER TABLE public.brand_rules ADD COLUMN IF NOT EXISTS version_no INT DEFAULT 1;")
                cur.execute("ALTER TABLE public.brand_rules ADD COLUMN IF NOT EXISTS allowed_numbers TEXT;")
                cur.execute("ALTER TABLE public.brand_rules ADD COLUMN IF NOT EXISTS applies_to VARCHAR(10) DEFAULT 'text';")
                cur.execute("ALTER TABLE public.facts ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(64) DEFAULT 'default';")
                cur.execute("ALTER TABLE public.scan_documents ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(64) DEFAULT 'default';")
                cur.execute("ALTER TABLE public.scan_documents ADD COLUMN IF NOT EXISTS channel VARCHAR(30) DEFAULT 'general';")
                cur.execute("ALTER TABLE public.scan_documents ADD COLUMN IF NOT EXISTS reaudit_needed BOOLEAN DEFAULT FALSE;")
                cur.execute("ALTER TABLE public.scan_documents ADD COLUMN IF NOT EXISTS reaudit_reason TEXT;")
                cur.execute("ALTER TABLE public.claim_evidence ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(64) DEFAULT 'default';")
                cur.execute("ALTER TABLE public.kb_chunks ADD COLUMN IF NOT EXISTS doc_title TEXT;")
                cur.execute("ALTER TABLE public.kb_chunks ADD COLUMN IF NOT EXISTS page_num INT DEFAULT 1;")
                cur.execute("ALTER TABLE public.kb_chunks ADD COLUMN IF NOT EXISTS paragraph_num INT DEFAULT 1;")
                cur.execute("ALTER TABLE public.kb_chunks ADD COLUMN IF NOT EXISTS chunk_text TEXT;")
                cur.execute("ALTER TABLE public.kb_chunks ADD COLUMN IF NOT EXISTS content_hash TEXT;")
                cur.execute("ALTER TABLE public.kb_chunks ADD COLUMN IF NOT EXISTS embedding JSONB;")
                cur.execute("ALTER TABLE public.kb_chunks ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(64) DEFAULT 'default';")
                cur.execute("ALTER TABLE public.kb_chunks ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;")

                cur.execute("DELETE FROM public.brand_rules")
                for r in RULES_DATA:
                    cur.execute("INSERT INTO public.brand_rules (rule_id,violation_type,severity,rule_cited,source_ref,rule_text,regex_pattern,default_fix,claim_status,allowed_numbers,applies_to,workspace_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (rule_id) DO UPDATE SET rule_text=EXCLUDED.rule_text", tuple(r.get(k) for k in ("rule_id", "violation_type", "severity", "rule_cited", "source_ref", "rule_text", "regex_pattern", "default_fix", "claim_status", "allowed_numbers", "applies_to", "workspace_id")))
                for f in FACTS_DATA:
                    cur.execute("INSERT INTO public.facts (fact_id,fact_text,source_ref,workspace_id) VALUES (%s,%s,%s,'default') ON CONFLICT (fact_id) DO UPDATE SET fact_text=EXCLUDED.fact_text,source_ref=EXCLUDED.source_ref", (f["fact_id"], f["fact_text"], f["source_ref"]))
                _seed_kb(conn)
                cur.execute("UPDATE public.kb_meta SET value=1 WHERE key='kb_version'")
                cur.execute("DELETE FROM public.scan_cache")
                for scan_id, text in demo_scans:
                    payload = main._mem_scans[scan_id]
                    cur.execute(
                        """INSERT INTO public.scans (scan_id, readiness_score, status, input_type, payload)
                           VALUES (%s, 100, 'approved', 'text', %s::jsonb)
                           ON CONFLICT (scan_id) DO UPDATE SET readiness_score=100, status='approved', payload=EXCLUDED.payload""",
                        (scan_id, json.dumps(payload)),
                    )
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
            print(f"[kb_router] reset_demo Neon DB write skipped or errored: {exc}")
        finally:
            conn.close()

    db._cache["at"] = 0
    db.get_vault(force=True)
    rules_router._memory_history.clear()
    rules_router._history_loaded.clear()
    cache.invalidate_cache()
    return {"status": "reset", "rules_version": 1, "kb_version": 1}
