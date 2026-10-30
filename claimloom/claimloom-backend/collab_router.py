"""Review comments, approvals, and public verification endpoints."""
from __future__ import annotations

import base64
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import db
import signing
from schemas import Issue, score_issues
from session import SessionUser, get_current_session, require_role

router = APIRouter()

# Useful for local development and when Neon is unavailable; production writes go to Neon.
_comments: List[Dict[str, Any]] = []
_approvals: List[Dict[str, Any]] = []
_approvals_loaded = False
_memory_versions: Dict[str, List[Dict[str, Any]]] = {}


def _sync_mem_scan(scan_id: str, data: dict) -> None:
    """Keep the shared scan lookup caches aligned with scan mutations."""
    try:
        import main
        main._mem_scans[scan_id] = data
    except Exception:
        pass
    try:
        import pdf_engine
        pdf_engine._mem_scan_json[scan_id] = data
    except Exception:
        pass


def _safe_connect():
    try:
        return db._connect()
    except Exception as exc:
        print(f"[collab_router] database connection fallback: {exc}")
        return None


class CommentRequest(BaseModel):
    comment_text: str = Field(..., min_length=1, max_length=4000)


class ApprovalRequest(BaseModel):
    version_no: Optional[int] = Field(default=None, ge=1)


class VersionRequest(BaseModel):
    text_snapshot: str = Field(..., max_length=20000)
    score: Optional[int] = Field(default=None, ge=0, le=100)


def _scan_data(scan_id: str) -> Dict[str, Any]:
    try:
        import pdf_engine
        scan = pdf_engine._load_scan_json(scan_id)
        if scan:
            return scan
    except Exception:
        pass
    conn = _safe_connect()
    if conn:
        try:
            with conn.cursor() as cur:
                try:
                    cur.execute("SELECT result_json, redacted_text, reaudit_needed, reaudit_reason FROM public.scan_documents WHERE scan_id = %s", (scan_id,))
                    has_reaudit_reason = True
                except Exception:
                    # Keep compatibility with databases that have not yet had
                    # the additive reaudit_reason migration applied.
                    conn.rollback()
                    cur.execute("SELECT result_json, redacted_text, reaudit_needed FROM public.scan_documents WHERE scan_id = %s", (scan_id,))
                    has_reaudit_reason = False
                row = cur.fetchone()
                if row:
                    result = row[0] if isinstance(row[0], dict) else json.loads(row[0])
                    result["redacted_text"] = row[1]
                    if row[2]:
                        note = row[3] if has_reaudit_reason else None
                        result["reaudit"] = {"needed": True, "note": note or "A cited source changed; this scan needs a new audit."}
                        result["status"] = "needs_reaudit"
                    return result
                cur.execute("SELECT payload FROM public.scans WHERE scan_id = %s", (scan_id,))
                row = cur.fetchone()
                if row and row[0]:
                    return row[0] if isinstance(row[0], dict) else json.loads(row[0])
        except Exception:
            pass
        finally:
            conn.close()
    raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found.")


def _iso(value: Any) -> str:
    if isinstance(value, datetime):
        # PostgreSQL TIMESTAMP WITHOUT TIME ZONE values come back naive. Our
        # approval timestamps are created in UTC, so interpret those as UTC
        # instead of letting the host's local timezone change the signed value.
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def _check_scan_workspace(scan: Dict[str, Any], session: SessionUser) -> None:
    scan_workspace = str(scan.get("workspace_id") or "default")
    if scan_workspace != session.workspace_id and session.role != "Admin":
        raise HTTPException(status_code=404, detail="Scan not found.")


def _latest_version(scan_id: str, scan: Dict[str, Any], requested: Optional[int]) -> Dict[str, Any]:
    versions = _memory_versions.get(scan_id)
    if versions is not None:
        candidates = [v for v in versions if requested is None or int(v["version_no"]) == requested]
        if candidates:
            return dict(candidates[-1])
        if requested not in (None, 1):
            raise HTTPException(status_code=404, detail=f"Scan version {requested} not found.")
        if requested == 1 and not versions:
            return {"version_no": 1, "text_snapshot": scan.get("redacted_text") or "", "score": int(scan.get("readiness_score") or 0)}
        if requested is None and not versions:
            return {"version_no": 1, "text_snapshot": scan.get("redacted_text") or "", "score": int(scan.get("readiness_score") or 0)}
        # Memory is authoritative once initialized; don't fetch the same rows repeatedly.
        raise HTTPException(status_code=404, detail=f"Scan version {requested} not found.")

    conn = _safe_connect()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT version_no, text_snapshot, score, actor_name, created_at FROM public.scan_versions WHERE scan_id = %s ORDER BY version_no ASC", (scan_id,))
                rows = cur.fetchall()
                if rows:
                    versions = [{"version_no": int(r[0]), "text_snapshot": r[1] or "", "score": int(r[2] or 0), "actor_name": r[3], "created_at": _iso(r[4])} for r in rows]
                    _memory_versions[scan_id] = versions
                    candidates = [v for v in versions if requested is None or v["version_no"] == requested]
                    if candidates:
                        return dict(candidates[-1])
        except Exception:
            pass
        finally:
            conn.close()
    versions = _memory_versions.get(scan_id, [])
    if versions:
        candidates = [v for v in versions if requested is None or v["version_no"] == requested]
        if candidates:
            return dict(candidates[-1])
    if requested not in (None, 1):
        raise HTTPException(status_code=404, detail=f"Scan version {requested} not found.")
    return {
        "version_no": 1,
        "text_snapshot": scan.get("redacted_text") or "",
        "score": int(scan.get("readiness_score") or 0),
    }


@router.post("/api/scans/{scan_id}/versions")
def create_scan_version(
    scan_id: str,
    req: VersionRequest,
    session: SessionUser = Depends(get_current_session),
):
    """Store an applied-fix snapshot for the reviewer's before/after diff."""
    scan = _scan_data(scan_id)
    _check_scan_workspace(scan, session)
    current = _latest_version(scan_id, scan, None)
    next_version = current["version_no"] + 1
    normalized_text = " ".join(req.text_snapshot.casefold().split())
    active_issue_models = []
    for raw_issue in scan.get("issues") or []:
        try:
            issue = Issue.model_validate(raw_issue)
            needle = " ".join(issue.flagged_text.casefold().split())
            if needle and needle in normalized_text:
                active_issue_models.append(issue)
        except Exception:
            continue
    calculated_score, calculated_pillars, calculated_status = score_issues(
        active_issue_models, ai_ok=scan.get("ai_status", "ok") == "ok"
    )
    updated = {
        **scan,
        "redacted_text": req.text_snapshot,
        "readiness_score": calculated_score,
        "pillar_scores": calculated_pillars.model_dump(),
        "status": calculated_status,
        "issues": [issue.model_dump() for issue in active_issue_models],
    }
    version_record = {
        "version_no": next_version,
        "text_snapshot": req.text_snapshot,
        "score": calculated_score,
        "actor_name": session.name,
        "created_at": signing.utc_timestamp(),
    }
    _memory_versions.setdefault(scan_id, []).append(version_record)
    _sync_mem_scan(scan_id, updated)

    def _persist_version() -> None:
        conn = _safe_connect()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO public.scan_versions (scan_id, version_no, text_snapshot, score, actor_name) VALUES (%s, %s, %s, %s, %s)",
                    (scan_id, next_version, req.text_snapshot, calculated_score, session.name),
                )
                cur.execute(
                    "UPDATE public.scan_documents SET redacted_text = %s, result_json = %s::jsonb WHERE scan_id = %s",
                    (req.text_snapshot, json.dumps(updated), scan_id),
                )
                cur.execute(
                    "UPDATE public.scans SET readiness_score = %s, payload = %s::jsonb WHERE scan_id = %s",
                    (calculated_score, json.dumps(updated), scan_id),
                )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"[collab_router] scan version persistence skipped: {exc}")
        finally:
            conn.close()

    import threading
    threading.Thread(target=_persist_version, daemon=True, name="scan-version-persist").start()
    return {"scan_id": scan_id, "version_no": next_version, "text_snapshot": req.text_snapshot, "score": calculated_score, "actor_name": session.name}


def _approval_rows(scan_id: Optional[str] = None) -> List[Dict[str, Any]]:
    global _approvals_loaded
    if not _approvals_loaded:
        conn = _safe_connect()
    else:
        conn = None
    if conn:
        try:
            with conn.cursor() as cur:
                query = "SELECT approval_id, scan_id, version_no, text_sha256, score, reviewer, role, prev_hash, entry_hash, signature, created_at FROM public.approvals"
                params: tuple = ()
                if scan_id is not None:
                    query += " WHERE scan_id = %s"
                    params = (scan_id,)
                query += " ORDER BY created_at ASC, approval_id ASC"
                cur.execute(query, params)
                rows = cur.fetchall()
                rows_out = [
                    {"approval_id": r[0], "scan_id": r[1], "version_no": int(r[2]), "text_sha256": r[3], "score": int(r[4]),
                     "reviewer": r[5], "role": r[6], "prev_hash": r[7], "entry_hash": r[8], "signature": r[9], "created_at": _iso(r[10])}
                    for r in rows
                ]
                _approvals[:] = rows_out
                _approvals_loaded = True
        except Exception:
            pass
        finally:
            conn.close()
    if not _approvals_loaded:
        _approvals_loaded = True
    rows = list(_approvals)
    return [a for a in rows if scan_id is None or a["scan_id"] == scan_id]


@router.post("/api/scans/{scan_id}/comments")
def add_comment(scan_id: str, req: CommentRequest, session: SessionUser = Depends(get_current_session)):
    _check_scan_workspace(_scan_data(scan_id), session)
    comment = {
        "scan_id": scan_id,
        "author_name": session.name,
        "author_role": session.role,
        "comment_text": req.comment_text.strip(),
        "created_at": signing.utc_timestamp(),
    }
    comment["comment_id"] = len(_comments) + 1
    _comments.append(comment)
    import threading

    def _persist_comment() -> None:
        conn = _safe_connect()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO public.scan_comments (scan_id, author_name, author_role, comment_text) VALUES (%s, %s, %s, %s)",
                    (scan_id, comment["author_name"], comment["author_role"], comment["comment_text"]),
                )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"[collab_router] comment persistence skipped: {exc}")
        finally:
            conn.close()

    threading.Thread(target=_persist_comment, daemon=True, name="scan-comment-persist").start()
    return {"status": "created", "comment": comment}


@router.get("/api/scans/{scan_id}/activity")
def scan_activity(scan_id: str, since: Optional[datetime] = Query(default=None), session: SessionUser = Depends(get_current_session)):
    scan = _scan_data(scan_id)
    _check_scan_workspace(scan, session)
    items: List[Dict[str, Any]] = []
    conn = _safe_connect()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT comment_id, author_name, author_role, comment_text, created_at FROM public.scan_comments WHERE scan_id = %s ORDER BY created_at ASC", (scan_id,))
                for row in cur.fetchall():
                    items.append({"type": "comment", "comment_id": row[0], "author_name": row[1], "author_role": row[2], "comment_text": row[3], "created_at": _iso(row[4])})
                cur.execute("SELECT version_no, text_snapshot, score, actor_name, created_at FROM public.scan_versions WHERE scan_id = %s ORDER BY version_no ASC", (scan_id,))
                for row in cur.fetchall():
                    items.append({"type": "version", "version_no": int(row[0]), "text_snapshot": row[1], "score": int(row[2]), "actor_name": row[3], "created_at": _iso(row[4])})
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Could not load scan activity: {exc}")
        finally:
            conn.close()
    else:
        items.extend({"type": "comment", **c} for c in _comments if c["scan_id"] == scan_id)
        items.extend({"type": "version", **v} for v in _memory_versions.get(scan_id, []))

    # Background writes may still be in flight when the UI polls activity.
    # Merge pending in-memory records with DB results while preserving repeated
    # identical comments as separate entries.
    db_comment_counts = Counter(
        (item.get("author_name"), item.get("author_role"), item.get("comment_text"))
        for item in items if item.get("type") == "comment"
    )
    for comment in _comments:
        if comment.get("scan_id") != scan_id:
            continue
        key = (comment.get("author_name"), comment.get("author_role"), comment.get("comment_text"))
        if db_comment_counts[key]:
            db_comment_counts[key] -= 1
        else:
            items.append({"type": "comment", **comment})

    db_version_numbers = {
        int(item["version_no"]) for item in items
        if item.get("type") == "version" and item.get("version_no") is not None
    }
    for version in _memory_versions.get(scan_id, []):
        if int(version["version_no"]) not in db_version_numbers:
            items.append({"type": "version", **version})
            db_version_numbers.add(int(version["version_no"]))
    items.extend({"type": "approval", **a} for a in _approval_rows(scan_id))
    if since:
        since_utc = since.astimezone(timezone.utc)
        items = [i for i in items if datetime.fromisoformat(_iso(i.get("created_at"))).astimezone(timezone.utc) > since_utc]
    items.sort(key=lambda i: i.get("created_at", ""))
    return {"scan_id": scan_id, "activity": items, "reaudit": scan.get("reaudit") or {"needed": False, "note": None}}


def _unresolved_high_issues(scan: Dict[str, Any], text: str) -> List[Dict[str, Any]]:
    normalized_text = " ".join((text or "").casefold().split())
    blockers = []
    for issue in scan.get("issues") or []:
        if str(issue.get("severity", "")).casefold() != "high":
            continue
        flagged = " ".join(str(issue.get("flagged_text") or "").casefold().split())
        if flagged and flagged in normalized_text:
            blockers.append(issue)
    return blockers


@router.post("/api/scans/{scan_id}/approve")
def approve_scan(
    scan_id: str,
    req: ApprovalRequest = ApprovalRequest(),
    session: SessionUser = Depends(require_role("Reviewer", "Admin")),
):
    global _approvals_loaded
    scan = _scan_data(scan_id)
    _check_scan_workspace(scan, session)
    if scan.get("status") == "needs_reaudit" or (scan.get("reaudit") or {}).get("needed"):
        raise HTTPException(status_code=409, detail="This scan needs a new audit before approval.")
    version = _latest_version(scan_id, scan, req.version_no)
    latest = _latest_version(scan_id, scan, None)
    if version["version_no"] != latest["version_no"]:
        raise HTTPException(status_code=409, detail="Only the latest scan version can be approved.")
    blockers = _unresolved_high_issues(scan, version["text_snapshot"])
    if blockers:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Resolve all High severity issues before approving this scan.",
                "unresolved_high_issues": [i.get("id") for i in blockers],
            },
        )
    text_sha = hashlib.sha256(version["text_snapshot"].encode("utf-8")).hexdigest()
    created_at = signing.utc_timestamp()
    prev_hash = _approvals[-1]["entry_hash"] if _approvals else None
    entry_hash = signing.approval_entry_hash(
        scan_id=scan_id, version_no=version["version_no"], text_sha256=text_sha,
        score=version["score"], reviewer=session.name, role=session.role,
        prev_hash=prev_hash, created_at=created_at,
    )
    approval = {
        "scan_id": scan_id, "version_no": version["version_no"], "text_sha256": text_sha,
        "score": version["score"], "reviewer": session.name, "role": session.role,
        "prev_hash": prev_hash, "entry_hash": entry_hash,
        "signature": signing.sign_entry_hash(entry_hash), "created_at": created_at,
        "approval_id": max((int(a.get("approval_id") or 0) for a in _approvals), default=0) + 1,
    }
    _approvals.append(approval)
    _approvals_loaded = True
    approved_scan = {**scan, "status": "approved", "readiness_score": version["score"]}
    _sync_mem_scan(scan_id, approved_scan)

    import threading

    def _persist_approval() -> None:
        conn = _safe_connect()
        if not conn:
            return
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_xact_lock(731204918)")
                cur.execute(
                    "INSERT INTO public.approvals (scan_id, version_no, text_sha256, score, reviewer, role, prev_hash, entry_hash, signature, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (scan_id, version["version_no"], text_sha, version["score"], session.name, session.role, prev_hash, entry_hash, approval["signature"], created_at),
                )
                cur.execute("UPDATE public.scan_documents SET result_json = %s::jsonb WHERE scan_id = %s", (json.dumps(approved_scan), scan_id))
                cur.execute("UPDATE public.scans SET status = 'approved', readiness_score = %s, payload = %s::jsonb WHERE scan_id = %s", (version["score"], json.dumps(approved_scan), scan_id))
            conn.commit()
        except Exception as exc:
            conn.rollback()
            print(f"[collab_router] approval persistence skipped: {exc}")
        finally:
            conn.close()

    threading.Thread(target=_persist_approval, daemon=True, name="scan-approval-persist").start()
    return {"status": "approved", "approval": approval, "public_key": signing.public_key_b64()}


@router.get("/api/verify/{scan_id}")
def verify_scan_approvals(scan_id: str):
    scan = _scan_data(scan_id)
    all_rows = _approval_rows()
    target_rows = [r for r in all_rows if r["scan_id"] == scan_id]
    if not target_rows:
        return {"scan_id": scan_id, "valid": False, "approvals": [], "reason": "No signed approval found."}

    versions_by_no: Dict[int, Dict[str, Any]] = {
        int(v["version_no"]): dict(v) for v in _memory_versions.get(scan_id, [])
    }
    conn = _safe_connect() if not versions_by_no else None
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT version_no, text_snapshot, score FROM public.scan_versions WHERE scan_id = %s ORDER BY version_no ASC",
                    (scan_id,),
                )
                versions_by_no = {
                    int(r[0]): {"version_no": int(r[0]), "text_snapshot": r[1] or "", "score": int(r[2] or 0)}
                    for r in cur.fetchall()
                }
        except Exception:
            versions_by_no = {}
        finally:
            conn.close()
    if not versions_by_no:
        versions_by_no = {int(v["version_no"]): dict(v) for v in _memory_versions.get(scan_id, [])}
    if not versions_by_no:
        versions_by_no[1] = {"version_no": 1, "text_snapshot": scan.get("redacted_text") or "", "score": int(scan.get("readiness_score") or 0)}

    all_entries_by_hash = {r["entry_hash"]: r for r in all_rows if r.get("entry_hash")}
    verified = []
    scan_chain_valid = True

    for i, row in enumerate(target_rows):
        calculated = signing.approval_entry_hash(
            scan_id=row["scan_id"], version_no=row["version_no"], text_sha256=row["text_sha256"],
            score=row["score"], reviewer=row["reviewer"], role=row["role"],
            prev_hash=row["prev_hash"], created_at=row["created_at"],
        )
        sig_valid = signing.verify_entry_hash(row["entry_hash"], row["signature"])
        hash_valid = (calculated == row["entry_hash"])

        try:
            signed_version = versions_by_no.get(int(row["version_no"]))
            if not signed_version:
                content_matches = False
            else:
                content_matches = (
                    hashlib.sha256(signed_version["text_snapshot"].encode("utf-8")).hexdigest()
                    == row["text_sha256"]
                )
        except Exception:
            content_matches = False

        if i == 0:
            if row.get("prev_hash"):
                pred = all_entries_by_hash.get(row["prev_hash"])
                link_valid = (pred is None or signing.verify_entry_hash(pred["entry_hash"], pred["signature"]))
            else:
                link_valid = True
        else:
            link_valid = (row.get("prev_hash") == target_rows[i - 1]["entry_hash"])

        row_valid = sig_valid and hash_valid and content_matches and link_valid
        if not (sig_valid and hash_valid and link_valid):
            scan_chain_valid = False

        verified.append({**row, "valid": row_valid, "content_matches": content_matches})

    latest_version = _latest_version(scan_id, scan, None)
    latest_approval = verified[-1] if verified else None
    tampered = bool(latest_approval and (
        not latest_approval["content_matches"]
        or latest_approval["version_no"] != latest_version["version_no"]
    ))
    chain_valid = scan_chain_valid and bool(verified)
    valid = bool(verified) and chain_valid and all(a["valid"] for a in verified) and not tampered

    return {
        "scan_id": scan_id,
        "valid": valid,
        "tampered": tampered,
        "chain_valid": chain_valid,
        "approvals": verified,
        "certificate": latest_approval,
        "public_key": signing.public_key_b64(),
    }


@router.get("/api/public-key")
def get_public_key():
    return {"algorithm": "Ed25519", "encoding": "base64-raw-32-byte", "public_key": signing.public_key_b64()}
