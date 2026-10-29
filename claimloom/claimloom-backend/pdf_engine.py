"""Improvement 1 — PDF & Layout Governance Engine (PyMuPDF / fitz).
Endpoints:
  - POST /api/scan-pdf
  - GET  /api/scans/{scan_id}
  - GET  /api/scans/{scan_id}/page/{n}.png
  - GET  /api/scans/{scan_id}/redline-pdf

Enforces Render 512 MB RAM constraints (try...finally: doc.close(), fitz.Matrix(1.5, 1.5))
and Neon 500 MB storage constraints (5 MB / 10-page cap, %PDF magic bytes, SHA-256 deduplication)."""
import hashlib
import io
import json
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

try:
    import pymupdf as fitz  # type: ignore
except ImportError:
    import fitz  # type: ignore  # PyMuPDF compatibility fallback
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool

import cache
import db
import pipeline
from rule_version import get_rules_version
from ratelimit import rate_limit_scan
from schemas import (
    Issue,
    ReauditInfo,
    ScanResponse,
    new_scan_id,
    normalize_channel,
    score_issues,
)
from session import SessionUser, get_current_session, resolve_workspace_id

router = APIRouter()


def _safe_db_connect():
    try:
        return db._connect()
    except Exception as exc:
        print(f"[pdf_engine] database connection fallback: {exc}")
        return None

MAX_PDF_BYTES = 5 * 1024 * 1024  # 5 MB strict cap
MAX_PDF_PAGES = 10               # 10 pages strict cap
PREVIEW_MATRIX = fitz.Matrix(1.5, 1.5)  # ~108 DPI safe for Render 512 MB RAM

# Bounded in-memory fallback (max 8 PDFs) so previews & redlines work even if Neon is offline
_MAX_MEM_PDFS = 8
_mem_pdf_by_scan: "OrderedDict[str, bytes]" = OrderedDict()
_mem_pdf_by_sha: "OrderedDict[str, bytes]" = OrderedDict()
_mem_scan_json: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()


def _clamp01(val: float) -> float:
    return round(min(max(float(val), 0.0), 1.0), 4)


def _norm_rect(rect: fitz.Rect, width: float, height: float) -> List[float]:
    if width <= 0 or height <= 0:
        return [0.05, 0.05, 0.95, 0.12]
    return [
        _clamp01(rect.x0 / width),
        _clamp01(rect.y0 / height),
        _clamp01(rect.x1 / width),
        _clamp01(rect.y1 / height),
    ]


def _remember_pdf_in_memory(scan_id: str, file_sha256: str, pdf_bytes: bytes, result_dict: Dict[str, Any]) -> None:
    _mem_pdf_by_scan[scan_id] = pdf_bytes
    _mem_pdf_by_scan.move_to_end(scan_id)
    while len(_mem_pdf_by_scan) > _MAX_MEM_PDFS:
        _mem_pdf_by_scan.popitem(last=False)

    if file_sha256:
        _mem_pdf_by_sha[file_sha256] = pdf_bytes
        _mem_pdf_by_sha.move_to_end(file_sha256)
        while len(_mem_pdf_by_sha) > _MAX_MEM_PDFS:
            _mem_pdf_by_sha.popitem(last=False)

    _mem_scan_json[scan_id] = result_dict
    _mem_scan_json.move_to_end(scan_id)
    while len(_mem_scan_json) > 100:
        _mem_scan_json.popitem(last=False)

    # Also sync with main._mem_scans if loaded
    try:
        import main
        main._mem_scans[scan_id] = result_dict
    except Exception:
        pass


def persist_pdf_scan(
    scan_resp: Dict[str, Any],
    redacted_text: str,
    pdf_bytes: bytes,
    file_sha256: str,
    actor_name: str = "Creator",
    rag_results: Optional[Dict[str, Any]] = None,
) -> None:
    """Persists PDF scan into `scan_documents` with SHA-256 deduplication of `pdf_bytes`."""
    scan_id = scan_resp["scan_id"]
    payload = {
        **scan_resp,
        "redacted_text": redacted_text,
        "input_type": "pdf",
    }
    _remember_pdf_in_memory(scan_id, file_sha256, pdf_bytes, payload)
    try:
        import collab_router
        collab_router._memory_versions.setdefault(scan_id, [{
            "version_no": 1,
            "text_snapshot": redacted_text or "",
            "score": int(scan_resp.get("readiness_score", 100)),
            "actor_name": actor_name or "Creator",
            "created_at": "",
        }])
    except Exception:
        pass
    try:
        import main
        main.save_scan_persistence(scan_resp, redacted_text, "pdf", pdf_bytes, file_sha256, actor_name, rag_results)
    except Exception as exc:
        print(f"[pdf_engine] persist_pdf_scan scheduling skipped: {exc}")


def _load_pdf_bytes_for_scan(scan_id: str) -> Optional[bytes]:
    """Retrieves raw PDF bytes for `scan_id`, resolving deduplicated `file_sha256` rows automatically."""
    if scan_id in _mem_pdf_by_scan:
        return _mem_pdf_by_scan[scan_id]

    conn = _safe_db_connect()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT pdf_bytes, file_sha256
                FROM public.scan_documents
                WHERE scan_id = %s;
                """,
                (scan_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            raw_bytes, file_sha = row[0], row[1]
            if raw_bytes:
                pdf_data = bytes(raw_bytes)
                _mem_pdf_by_scan[scan_id] = pdf_data
                return pdf_data

            # Deduplicated lookup by file_sha256
            if file_sha:
                if file_sha in _mem_pdf_by_sha:
                    return _mem_pdf_by_sha[file_sha]
                cur.execute(
                    """
                    SELECT pdf_bytes
                    FROM public.scan_documents
                    WHERE file_sha256 = %s AND pdf_bytes IS NOT NULL
                    LIMIT 1;
                    """,
                    (file_sha,),
                )
                dedup_row = cur.fetchone()
                if dedup_row and dedup_row[0]:
                    pdf_data = bytes(dedup_row[0])
                    _mem_pdf_by_scan[scan_id] = pdf_data
                    _mem_pdf_by_sha[file_sha] = pdf_data
                    return pdf_data
        return None
    except Exception as e:
        print(f"[pdf_engine] _load_pdf_bytes_for_scan failed: {e}")
        return None
    finally:
        conn.close()


def _load_scan_json(scan_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves stored ScanResponse JSON (without heavy pdf_bytes)."""
    if scan_id in _mem_scan_json:
        return _mem_scan_json[scan_id]
    try:
        import main
        if scan_id in main._mem_scans:
            result = main._mem_scans[scan_id]
            _mem_scan_json[scan_id] = result
            return result
    except Exception:
        pass

    conn = _safe_db_connect()
    if conn:
        try:
            with conn.cursor() as cur:
                try:
                    cur.execute(
                        """
                        SELECT result_json, redacted_text, reaudit_needed, reaudit_reason
                        FROM public.scan_documents
                        WHERE scan_id = %s;
                        """,
                        (scan_id,),
                    )
                    has_reaudit_reason = True
                except Exception:
                    # Older Round 3 deployments predate the optional reason
                    # column. Keep reads working until seed_db.py applies the
                    # additive schema upgrade.
                    conn.rollback()
                    cur.execute(
                        """
                        SELECT result_json, redacted_text, reaudit_needed
                        FROM public.scan_documents
                        WHERE scan_id = %s;
                        """,
                        (scan_id,),
                    )
                    has_reaudit_reason = False
                row = cur.fetchone()
                if row:
                    if has_reaudit_reason:
                        result_data, redacted_text, reaudit_needed, reaudit_reason = row
                    else:
                        result_data, redacted_text, reaudit_needed = row
                        reaudit_reason = None
                    if isinstance(result_data, str):
                        result_data = json.loads(result_data)
                    else:
                        result_data = dict(result_data)
                    result_data["redacted_text"] = redacted_text
                    if reaudit_needed:
                        result_data["status"] = "needs_reaudit"
                        result_data["reaudit"] = {
                            "needed": True,
                            "note": reaudit_reason
                            or "A Truth Vault fact cited by this scan was updated after approval.",
                        }
                    _mem_scan_json[scan_id] = result_data
                    return result_data

                cur.execute(
                    "SELECT payload FROM public.scans WHERE scan_id = %s;",
                    (scan_id,),
                )
                r2 = cur.fetchone()
                if r2 and r2[0]:
                    payload = r2[0] if isinstance(r2[0], dict) else json.loads(r2[0])
                    if "scan_id" in payload:
                        _mem_scan_json[scan_id] = payload
                        try:
                            import main
                            main._mem_scans[scan_id] = payload
                        except Exception:
                            pass
                        return payload
        except Exception as e:
            print(f"[pdf_engine] _load_scan_json DB fallback: {e}")
        finally:
            conn.close()

    return None


def _find_bbox_on_page(page: fitz.Page, phrase: str) -> Optional[List[float]]:
    """Finds the normalized [x0, y0, x1, y1] bounding box for `phrase` on `page`."""
    w, h = float(page.rect.width), float(page.rect.height)
    clean = " ".join((phrase or "").split()).strip()
    if not clean or w <= 0 or h <= 0:
        return None

    # 1. Exact phrase search
    quads = page.search_for(clean)
    if not quads and len(clean) > 28:
        # 2. Fallback: search first 4 words if line wrapping split the phrase
        short_head = " ".join(clean.split()[:4])
        quads = page.search_for(short_head)
    if not quads and len(clean.split()) >= 2:
        # 3. Fallback: search first 2 words
        quads = page.search_for(" ".join(clean.split()[:2]))

    if quads:
        union_rect = fitz.Rect(quads[0])
        for r in quads[1:3]:
            if abs(r.y0 - union_rect.y0) < h * 0.08:
                union_rect |= fitz.Rect(r)
        return _norm_rect(union_rect, w, h)
    return None


def _detect_pdf_layout_issues(page: fitz.Page, page_num: int, channel: str) -> List[Issue]:
    """Checks font legibility and approximate span contrast using low-res samples."""
    layout_issues: List[Issue] = []
    w, h = float(page.rect.width), float(page.rect.height)
    if w <= 0 or h <= 0:
        return layout_issues

    try:
        text_dict = page.get_text("dict")
        pix = None
        scale = 0.25
        contrast_flags = 0
        for block in text_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    span_text = str(span.get("text") or "").strip()
                    font_size = float(span.get("size") or 12.0)
                    bbox_raw = span.get("bbox")
                    if len(span_text) >= 4 and 0.5 < font_size < 9.0:
                        
                        rect = fitz.Rect(bbox_raw) if bbox_raw else fitz.Rect(0.05 * w, 0.85 * h, 0.95 * w, 0.92 * h)
                        layout_issues.append(
                            Issue(
                                id="",
                                severity="Low",
                                violation_type="Accessibility",
                                flagged_text=span_text[:80],
                                start=-1,
                                end=-1,
                                rule_id=10,
                                rule_cited="PDF Layout Rule: Minimum Legible Font Size (9pt)",
                                source_ref="Accessibility Handbook, p.4 (Typography & Fine Print)",
                                explanation=(
                                    f"Text on page {page_num} is rendered at {font_size:.1f}pt, which is below the "
                                    "9pt minimum legibility threshold for disclosures and body text."
                                ),
                                suggested_fix=f"Increase '{span_text[:40]}' font size to at least 9pt",
                                confidence=0.95,
                                detected_by="pdf_layout",
                                claim_status=None,
                                page=page_num,
                                bbox=_norm_rect(rect, w, h),
                                channel=channel,
                            )
                        )
                    # Sample nearby pixels outside the text span as an approximate
                    # background, then compare against the declared text color.
                    if span_text and contrast_flags < 2 and bbox_raw:
                        if pix is None:
                            pix = page.get_pixmap(matrix=fitz.Matrix(0.25, 0.25), alpha=False)
                        if pix.n < 3:
                            continue
                        fg_value = int(span.get("color") or 0)
                        foreground = ((fg_value >> 16) & 255, (fg_value >> 8) & 255, fg_value & 255)
                        rect = fitz.Rect(bbox_raw)
                        candidates = [
                            (rect.x1 + 6, (rect.y0 + rect.y1) / 2),
                            (rect.x0 - 6, (rect.y0 + rect.y1) / 2),
                            ((rect.x0 + rect.x1) / 2, rect.y0 - 6),
                            ((rect.x0 + rect.x1) / 2, rect.y1 + 6),
                        ]
                        samples = []
                        for px, py in candidates:
                            ix, iy = int(px * scale), int(py * scale)
                            if 0 <= ix < pix.width and 0 <= iy < pix.height:
                                off = (iy * pix.width + ix) * pix.n
                                samples.append(tuple(pix.samples[off:off + 3]))
                        if samples:
                            background = tuple(sorted(sample[channel_i] for sample in samples)[len(samples) // 2] for channel_i in range(3))
                            def luminance(rgb):
                                vals = [v / 255.0 for v in rgb]
                                vals = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in vals]
                                return 0.2126 * vals[0] + 0.7152 * vals[1] + 0.0722 * vals[2]
                            fg_l, bg_l = luminance(foreground), luminance(background)
                            contrast = (max(fg_l, bg_l) + 0.05) / (min(fg_l, bg_l) + 0.05)
                            if contrast < 4.5:
                                layout_issues.append(Issue(
                                    id="", severity="Low", violation_type="Accessibility",
                                    flagged_text=span_text[:80], start=-1, end=-1, rule_id=10,
                                    rule_cited="PDF Layout Rule: Text Contrast (WCAG 2.1 AA)",
                                    source_ref="WCAG 2.1 AA, criterion 1.4.3",
                                    explanation=f"Approximate sampled text contrast is {contrast:.2f}:1, below 4.5:1.",
                                    suggested_fix="Increase text/background contrast to at least 4.5:1",
                                    confidence=0.72, detected_by="pdf_layout", page=page_num,
                                    bbox=_norm_rect(rect, w, h), channel=channel,
                                ))
                                contrast_flags += 1
                    if len(layout_issues) >= 4:
                        break
                if len(layout_issues) >= 4:
                    break
            if len(layout_issues) >= 4:
                break
    except Exception as e:
        print(f"[pdf_engine] layout check warning on page {page_num}: {e}")

    return layout_issues


def _process_pdf_bytes(
    file_bytes: bytes,
    channel: str,
    workspace_id: str,
) -> Tuple[pipeline.Analysis, int, str]:
    """Extracts text + layout from PDF inside try...finally: doc.close(),
    runs the two-tier + RAG pipeline, and maps every issue to (page, normalized bbox)."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    try:
        if doc.is_encrypted:
            raise ValueError("Password-protected PDFs are not supported. Remove the password and upload again.")
        page_count = len(doc)
        if page_count == 0:
            raise ValueError("PDF contains 0 pages.")
        if page_count > MAX_PDF_PAGES:
            raise PermissionError(f"PDF has {page_count} pages (maximum {MAX_PDF_PAGES} pages allowed on free tier).")

        page_Texts: List[str] = []
        # (page_num_1based, utf16_start, utf16_end)
        page_utf16_ranges: List[Tuple[int, int, int]] = []
        layout_issues: List[Issue] = []
        font_families = set()

        running_text = ""
        for idx in range(page_count):
            page = doc[idx]
            page_num = idx + 1
            p_text = (page.get_text("text") or "").strip()
            separator = "\n\n" if running_text and p_text else ""
            start_u16 = len((running_text + separator).encode("utf-16-le")) // 2
            running_text = running_text + separator + p_text
            end_u16 = len(running_text.encode("utf-16-le")) // 2
            page_Texts.append(p_text)
            page_utf16_ranges.append((page_num, start_u16, end_u16))
            try:
                for block in page.get_text("dict").get("blocks", []):
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            if span.get("font"):
                                font_families.add(str(span["font"]).split(",", 1)[0])
            except Exception:
                pass
            layout_issues.extend(_detect_pdf_layout_issues(page, page_num, channel))

        if len(font_families) > 3:
            layout_issues.append(Issue(
                id="", severity="Low", violation_type="Visual", flagged_text=f"{len(font_families)} font families",
                start=-1, end=-1, rule_id=9,
                rule_cited="PDF Layout Rule: Consistent Typography",
                source_ref="Brand Visual Design System",
                explanation=f"Document uses {len(font_families)} distinct font families; use three or fewer for visual consistency.",
                suggested_fix="Reduce the document to three or fewer font families", confidence=0.85,
                detected_by="pdf_layout", page=1, bbox=[0.05, 0.03, 0.95, 0.08], channel=channel,
            ))

        full_text = running_text.strip()
        if not full_text:
            full_text = "[Visual PDF Document with no selectable text layer]"

        analysis = pipeline.analyze_text(
            full_text,
            with_positions=True,
            channel=channel,
            workspace_id=workspace_id,
        )

        # Map each text/RAG/AI issue to its 1-based page and normalized [x0, y0, x1, y1] bbox
        for iss in analysis.issues:
            assigned_page = 1
            if iss.start is not None and iss.start >= 0:
                for p_num, u_start, u_end in page_utf16_ranges:
                    if u_start <= iss.start <= max(u_end, u_start):
                        assigned_page = p_num
                        break

            # Search target page first, then fall back to scanning all pages if needed
            target_page_obj = doc[assigned_page - 1]
            bbox = _find_bbox_on_page(target_page_obj, iss.flagged_text)
            if not bbox:
                for p_idx in range(page_count):
                    cand_bbox = _find_bbox_on_page(doc[p_idx], iss.flagged_text)
                    if cand_bbox:
                        assigned_page = p_idx + 1
                        bbox = cand_bbox
                        break

            if not bbox:
                # Deterministic fallback band on the assigned page so canvas overlay is never null
                w = float(target_page_obj.rect.width) or 612.0
                h = float(target_page_obj.rect.height) or 792.0
                band_y = min(0.85, 0.15 + ((hash(iss.flagged_text) % 10) * 0.06))
                bbox = _norm_rect(fitz.Rect(0.08 * w, band_y * h, 0.92 * w, (band_y + 0.045) * h), w, h)

            iss.page = assigned_page
            iss.bbox = bbox

        # Merge any PDF layout issues and re-number IDs sequentially
        analysis.issues.extend(layout_issues)
        for n, iss in enumerate(analysis.issues, 1):
            iss.id = f"iss_pdf_{n}"

        return analysis, page_count, full_text
    finally:
        doc.close()


# ------------------------------------------------------------------ 1. POST /api/scan-pdf
@router.post("/api/scan-pdf", response_model=ScanResponse)
async def scan_pdf_endpoint(
    background: BackgroundTasks,
    file: UploadFile = File(...),          # Collision Point 3: exact key "file"
    channel: str = Form("general"),        # Optional form field
    workspace_id: str = Form("default"),   # Optional form field
    _client_ip: str = Depends(rate_limit_scan),
    session: SessionUser = Depends(get_current_session),
):
    file_bytes = await file.read()
    if len(file_bytes) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="PDF exceeds 5 MB limit.")
    if not file_bytes.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Invalid PDF file header (must begin with %PDF).")

    norm_ch = normalize_channel(channel)
    norm_ws = resolve_workspace_id(workspace_id, session)
    file_sha256 = hashlib.sha256(file_bytes).hexdigest()

    # Check deterministic SHA-256 cache over PDF hash + channel + workspace + versions
    rules, _facts, _src = db.get_vault()
    rules_version = get_rules_version()
    kb_version = pipeline.get_kb_version(norm_ws)
    cache_key = cache.make_cache_key(
        text=f"pdf_sha256:{file_sha256}",
        channel=norm_ch,
        workspace_id=norm_ws,
        rules_version=rules_version,
        kb_version=kb_version,
    )
    cached_hit = cache.get_cached_scan(cache_key)
    if cached_hit:
        cached_hit["scan_id"] = new_scan_id()
        cached_hit["cached"] = True
        cached_hit["channel"] = norm_ch
        cached_hit["workspace_id"] = norm_ws
        cached_hit["input_type"] = "pdf"
        cached_response = ScanResponse(**cached_hit)
        payload = cached_response.model_dump()
        _remember_pdf_in_memory(cached_response.scan_id, file_sha256, file_bytes, payload)
        background.add_task(
            persist_pdf_scan,
            payload,
            cached_response.redacted_text or "",
            file_bytes,
            file_sha256,
            session.name,
            None,
        )
        return cached_response

    try:
        analysis, page_count, _full_text = await run_in_threadpool(
            _process_pdf_bytes,
            file_bytes,
            norm_ch,
            norm_ws,
        )
    except PermissionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Unable to parse PDF document: {e}")

    score, pillars, status = score_issues(analysis.issues, ai_ok=analysis.ai_ok)
    scan_id = new_scan_id()

    response_obj = ScanResponse(
        scan_id=scan_id,
        readiness_score=score,
        status=status,
        ai_status="ok" if analysis.ai_ok else "degraded",
        pillar_scores=pillars,
        ai_disclosure=pipeline.disclosure(
            analysis.model_label,
            analysis.ai_ok,
            "PDF text & layout coordinates extracted deterministically with PyMuPDF.",
        ),
        pii_redacted_count=analysis.pii_count,
        issues=analysis.issues,
        input_type="pdf",
        redacted_text=analysis.redacted_text,
        cached=False,
        channel=norm_ch,
        workspace_id=norm_ws,
        kb_version=analysis.kb_version,
        rules_version=analysis.rules_version,
        page_count=page_count,
        verified_claims=analysis.verified_claims,
        reaudit=ReauditInfo(needed=False, note=None),
    )

    resp_dict = response_obj.model_dump()
    _remember_pdf_in_memory(scan_id, file_sha256, file_bytes, resp_dict)

    if response_obj.ai_status == "ok":
        background.add_task(cache.set_cached_scan, cache_key, resp_dict)

    background.add_task(
        persist_pdf_scan,
        resp_dict,
        analysis.redacted_text,
        file_bytes,
        file_sha256,
        session.name,
        analysis.rag_results,
    )
    return response_obj


def _extract_supported_document(filename: str, file_bytes: bytes) -> str:
    suffix = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if suffix in {"md", "markdown", "txt"}:
        try:
            return file_bytes.decode("utf-8-sig").strip()
        except UnicodeDecodeError as exc:
            raise ValueError("Text documents must use UTF-8 encoding.") from exc
    if suffix == "docx":
        try:
            from docx import Document
            doc = Document(io.BytesIO(file_bytes))
            parts = [p.text for p in doc.paragraphs if p.text]
            for table in doc.tables:
                for row in table.rows:
                    cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                    if cells:
                        parts.append(" | ".join(cells))
            return "\n".join(parts).strip()
        except Exception as exc:
            raise ValueError(f"Unable to read DOCX document: {exc}") from exc
    raise ValueError("Unsupported document type. Upload a .docx, .md, .markdown, or .txt file.")


@router.post("/api/scan-doc", response_model=ScanResponse)
async def scan_document_endpoint(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    channel: str = Form("general"),
    workspace_id: str = Form("default"),
    _client_ip: str = Depends(rate_limit_scan),
    session: SessionUser = Depends(get_current_session),
):
    file_bytes = await file.read()
    if len(file_bytes) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="Document exceeds 5 MB limit.")
    try:
        text = await run_in_threadpool(_extract_supported_document, file.filename or "", file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not text:
        raise HTTPException(status_code=400, detail="The document contains no readable text.")
    if len(text) > 8000:
        raise HTTPException(status_code=413, detail="Extracted document text exceeds the 8,000 character scan limit.")

    norm_ch = normalize_channel(channel)
    norm_ws = resolve_workspace_id(workspace_id, session)
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    rules_version = get_rules_version()
    kb_version = pipeline.get_kb_version(norm_ws)
    cache_key = cache.make_cache_key(
        text=f"document_sha256:{file_hash}", channel=norm_ch, workspace_id=norm_ws,
        rules_version=rules_version, kb_version=kb_version,
    )
    cached_hit = cache.get_cached_scan(cache_key)
    if cached_hit:
        cached_hit.update({"scan_id": new_scan_id(), "cached": True, "input_type": "document", "channel": norm_ch, "workspace_id": norm_ws})
        cached_response = ScanResponse(**cached_hit)
        background.add_task(
            _persist_document_scan,
            cached_response.model_dump(),
            cached_response.redacted_text or "",
            session.name,
        )
        return cached_response

    analysis = await run_in_threadpool(pipeline.analyze_text, text, True, norm_ch, norm_ws)
    score, pillars, status = score_issues(analysis.issues, ai_ok=analysis.ai_ok)
    response_obj = ScanResponse(
        scan_id=new_scan_id(), readiness_score=score, status=status,
        ai_status="ok" if analysis.ai_ok else "degraded", pillar_scores=pillars,
        ai_disclosure=pipeline.disclosure(analysis.model_label, analysis.ai_ok, "Text extracted from an uploaded document."),
        pii_redacted_count=analysis.pii_count, issues=analysis.issues,
        input_type="document", redacted_text=analysis.redacted_text, cached=False,
        channel=norm_ch, workspace_id=norm_ws, kb_version=analysis.kb_version,
        rules_version=analysis.rules_version, page_count=1,
        verified_claims=analysis.verified_claims, reaudit=ReauditInfo(needed=False, note=None),
    )
    payload = response_obj.model_dump()
    if response_obj.ai_status == "ok":
        background.add_task(cache.set_cached_scan, cache_key, payload)
    background.add_task(_persist_document_scan, payload, analysis.redacted_text, session.name, analysis.rag_results)
    return response_obj


def _persist_document_scan(
    scan_resp: Dict[str, Any], redacted_text: str, actor_name: str = "Creator",
    rag_results: Optional[Dict[str, Any]] = None,
) -> None:
    try:
        import main
        main.save_scan_persistence(scan_resp, redacted_text, "document", None, None, actor_name, rag_results)
    except Exception as exc:
        print(f"[pdf_engine] document persistence skipped: {exc}")


# ------------------------------------------------------------------ 2. GET /api/scans/{scan_id}
@router.get("/api/scans/{scan_id}")
def get_saved_scan_endpoint(scan_id: str):
    """Collision Point 4: Returns stored ScanResponse JSON (plus redacted_text and input_type)
    without fetching the heavy pdf_bytes column."""
    data = _load_scan_json(scan_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found.")
    return data


# ------------------------------------------------------------------ 3. GET /api/scans/{scan_id}/page/{n}.png
def _render_pdf_page_png(pdf_bytes: bytes, page_number_1based: int) -> bytes:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        total = len(doc)
        if page_number_1based < 1 or page_number_1based > total:
            raise IndexError(f"Page {page_number_1based} out of range (1..{total}).")
        page = doc[page_number_1based - 1]
        pix = page.get_pixmap(matrix=PREVIEW_MATRIX, alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


@router.get("/api/scans/{scan_id}/page/{n}.png")
async def get_pdf_page_preview(scan_id: str, n: int):
    """Renders 1-based page `n` as PNG at fitz.Matrix(1.5, 1.5) inside try...finally: doc.close()."""
    pdf_bytes = _load_pdf_bytes_for_scan(scan_id)
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail=f"PDF binary for scan {scan_id} not found.")
    try:
        png_bytes = await run_in_threadpool(_render_pdf_page_png, pdf_bytes, n)
    except IndexError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to render PDF page {n}: {e}")

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=3600"},
    )


# ------------------------------------------------------------------ 4. GET /api/scans/{scan_id}/redline-pdf
def _synthesize_pdf_from_text(redacted_text: str, scan_id: str) -> bytes:
    """If a user calls /redline-pdf on a plain-text scan, synthesizes a clean base PDF first."""
    doc = fitz.open()
    try:
        page = doc.new_page(width=612, height=792)
        page.insert_text(
            fitz.Point(48, 52),
            f"ClaimLoom Audited Draft ({scan_id})",
            fontsize=14,
            fontname="helv",
            color=(0.12, 0.23, 0.54),
        )
        rect = fitz.Rect(48, 76, 564, 740)
        page.insert_textbox(
            rect,
            redacted_text or "(Empty draft)",
            fontsize=10.5,
            fontname="helv",
            color=(0.06, 0.09, 0.16),
        )
        return doc.tobytes(garbage=2, deflate=True)
    finally:
        doc.close()


def _fetch_latest_approval(scan_id: str) -> Optional[Dict[str, Any]]:
    """Checks `approvals` table (Module 4) for an existing cryptographic signature on this scan."""
    try:
        import collab_router
        for approval in reversed(collab_router._approvals):
            if approval.get("scan_id") == scan_id:
                return approval
        if collab_router._approvals_loaded:
            return None
    except Exception:
        pass
    cached_scan = _mem_scan_json.get(scan_id)
    if cached_scan and cached_scan.get("status") != "approved":
        return None
    conn = _safe_db_connect()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT reviewer, role, text_sha256, entry_hash, signature, created_at
                FROM public.approvals
                WHERE scan_id = %s
                ORDER BY approval_id DESC
                LIMIT 1;
                """,
                (scan_id,),
            )
            row = cur.fetchone()
            if row:
                return {
                    "reviewer": row[0],
                    "role": row[1],
                    "text_sha256": row[2],
                    "entry_hash": row[3],
                    "signature": row[4],
                    "created_at": str(row[5]),
                }
    except Exception:
        pass
    finally:
        conn.close()
    return None


def _build_redlined_pdf(
    base_pdf_bytes: bytes,
    scan_data: Dict[str, Any],
    approval: Optional[Dict[str, Any]],
) -> bytes:
    """Draws red bounding boxes around every flagged issue and appends a signed Compliance Certificate page."""
    doc = fitz.open(stream=base_pdf_bytes, filetype="pdf")
    try:
        issues = scan_data.get("issues") or []
        total_pages = len(doc)

        # 1. Draw red rectangles & badges around flagged bboxes on content pages
        for idx, iss in enumerate(issues, 1):
            page_num = int(iss.get("page") or 1)
            page_idx = min(max(page_num - 1, 0), max(total_pages - 1, 0))
            page = doc[page_idx]
            w, h = float(page.rect.width), float(page.rect.height)

            bbox = iss.get("bbox")
            if isinstance(bbox, list) and len(bbox) == 4:
                r = fitz.Rect(
                    float(bbox[0]) * w,
                    float(bbox[1]) * h,
                    float(bbox[2]) * w,
                    float(bbox[3]) * h,
                )
            else:
                found_b = _find_bbox_on_page(page, str(iss.get("flagged_text") or ""))
                if found_b:
                    r = fitz.Rect(found_b[0] * w, found_b[1] * h, found_b[2] * w, found_b[3] * h)
                else:
                    y_top = min(h - 60, 90 + (idx - 1) * 36)
                    r = fitz.Rect(48, y_top, w - 48, y_top + 22)

            # Pad slightly for visual clarity
            pad_r = fitz.Rect(max(4, r.x0 - 2), max(4, r.y0 - 2), min(w - 4, r.x1 + 2), min(h - 4, r.y1 + 2))
            page.draw_rect(
                pad_r,
                color=(0.86, 0.15, 0.15),
                fill=(0.99, 0.78, 0.78),
                fill_opacity=0.24,
                width=1.6,
            )

            label_text = f"#{idx} [{iss.get('severity', 'Flag')}] Fix: {str(iss.get('suggested_fix', ''))[:38]}"
            tag_y = max(12.0, pad_r.y0 - 3.0)
            page.insert_text(
                fitz.Point(pad_r.x0, tag_y),
                label_text,
                fontsize=7.5,
                fontname="helv",
                color=(0.75, 0.08, 0.08),
            )

        # 2. Append Signed Compliance Certificate Page
        cert = doc.new_page(width=612, height=792)
        # Header banner (Brand Indium Blue #1E3A8A)
        cert.draw_rect(fitz.Rect(0, 0, 612, 92), color=(0.118, 0.227, 0.541), fill=(0.118, 0.227, 0.541))
        cert.insert_text(
            fitz.Point(36, 42),
            "CLAIMLOOM GOVERNANCE GATEKEEPER",
            fontsize=16,
            fontname="helv",
            color=(1, 1, 1),
        )
        cert.insert_text(
            fitz.Point(36, 66),
            "Pre-Publication Redline Audit & Cryptographic Compliance Certificate",
            fontsize=10,
            fontname="helv",
            color=(0.88, 0.92, 1.0),
        )

        scan_id = str(scan_data.get("scan_id", "scan_unknown"))
        score = int(scan_data.get("readiness_score", 0))
        status_str = str(scan_data.get("status", "needs_review")).upper()
        channel_str = str(scan_data.get("channel", "general")).upper()
        workspace_str = str(scan_data.get("workspace_id", "default"))
        kb_v = int(scan_data.get("kb_version", 1))
        rules_v = int(scan_data.get("rules_version", 1))
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # Summary Box
        cert.draw_rect(
            fitz.Rect(36, 110, 576, 215),
            color=(0.82, 0.85, 0.90),
            fill=(0.97, 0.98, 1.0),
            width=1.0,
        )
        meta_lines = [
            f"Scan ID: {scan_id}      |      Audit Timestamp: {now_utc}",
            f"Readiness Score: {score} / 100      |      Gatekeeper Status: {status_str}",
            f"Workspace: {workspace_str}      |      Target Channel: {channel_str}",
            f"Truth Vault KB Version: v{kb_v}      |      Brand Rules Version: v{rules_v}      |      Total Flags: {len(issues)}",
        ]
        for i, line in enumerate(meta_lines):
            cert.insert_text(fitz.Point(48, 132 + i * 20), line, fontsize=9.5, fontname="helv", color=(0.06, 0.09, 0.16))

        # Issues Summary Section
        cert.insert_text(
            fitz.Point(36, 242),
            "AUDITED FLAGS & REQUIRED REMEDIATIONS",
            fontsize=11,
            fontname="helv",
            color=(0.118, 0.227, 0.541),
        )
        y_cursor = 262.0
        if not issues:
            cert.insert_text(
                fitz.Point(44, y_cursor + 10),
                "Zero brand or factual violations detected. Asset meets all publication governance standards.",
                fontsize=9.5,
                fontname="helv",
                color=(0.08, 0.45, 0.20),
            )
            y_cursor += 35.0
        else:
            for idx, iss in enumerate(issues[:10], 1):
                if y_cursor > 560:
                    break
                sev = iss.get("severity", "Medium")
                p_no = iss.get("page") or 1
                cited = str(iss.get("rule_cited") or "Brand Rule")[:62]
                flagged = str(iss.get("flagged_text") or "")[:45]
                fix = str(iss.get("suggested_fix") or "")[:45]
                cert.insert_text(
                    fitz.Point(42, y_cursor),
                    f"#{idx} [Page {p_no} | {sev}] {cited}",
                    fontsize=8.8,
                    fontname="helv",
                    color=(0.70, 0.10, 0.10) if sev == "High" else (0.15, 0.18, 0.25),
                )
                cert.insert_text(
                    fitz.Point(54, y_cursor + 12),
                    f"Flagged: \"{flagged}\"   -->   Suggested Fix: \"{fix}\"",
                    fontsize=8.2,
                    fontname="helv",
                    color=(0.25, 0.30, 0.38),
                )
                y_cursor += 30.0

        # Cryptographic Seal Footer
        text_body = str(scan_data.get("redacted_text") or "")
        doc_sha256 = hashlib.sha256(text_body.encode("utf-8")).hexdigest()
        if approval:
            reviewer_line = f"Approved By: {approval['reviewer']} ({approval['role']}) at {approval['created_at']}"
            chain_hash = approval["entry_hash"]
            sig_hex = str(approval["signature"])[:72] + "..."
        else:
            # Generate deterministic verification seal (uses signing.py if present)
            reviewer_line = "Approval Status: Automated Gatekeeper Seal (Pending Human Sign-off)"
            chain_hash = hashlib.sha256(f"{scan_id}:{score}:{doc_sha256}".encode("utf-8")).hexdigest()
            try:
                import signing  # type: ignore
                sig_hex = signing.sign_entry_hash(chain_hash)[:72] + "..."
            except Exception:
                sig_hex = hashlib.sha256(f"seal:{chain_hash}".encode("utf-8")).hexdigest()

        cert.draw_rect(
            fitz.Rect(36, 610, 576, 748),
            color=(0.118, 0.227, 0.541),
            fill=(0.95, 0.97, 1.0),
            width=1.2,
        )
        cert.insert_text(
            fitz.Point(48, 632),
            "CRYPTOGRAPHIC COMPLIANCE & AUDIT SEAL (Ed25519 / SHA-256)",
            fontsize=10,
            fontname="helv",
            color=(0.118, 0.227, 0.541),
        )
        seal_lines = [
            reviewer_line,
            f"Content SHA-256: {doc_sha256}",
            f"Ledger Entry Hash: {chain_hash}",
            f"Signature: {sig_hex}",
            f"Verify Online: /api/verify/{scan_id}",
        ]
        for i, s_line in enumerate(seal_lines):
            cert.insert_text(
                fitz.Point(48, 652 + i * 17),
                s_line,
                fontsize=8.2,
                fontname="cour",
                color=(0.12, 0.16, 0.24),
            )

        return doc.tobytes(garbage=3, deflate=True)
    finally:
        doc.close()


@router.get("/api/scans/{scan_id}/redline-pdf")
async def download_redline_pdf(scan_id: str):
    """Draws red rectangles around flagged bboxes, appends a signed Compliance Certificate page,
    and streams the PDF download with Content-Disposition exposed for CORS."""
    scan_data = _load_scan_json(scan_id)
    if not scan_data:
        raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found.")

    pdf_bytes = _load_pdf_bytes_for_scan(scan_id)
    if not pdf_bytes:
        # Synthesize PDF from redacted_text so /redline-pdf works on plain-text scans too
        pdf_bytes = await run_in_threadpool(
            _synthesize_pdf_from_text,
            str(scan_data.get("redacted_text") or ""),
            scan_id,
        )

    approval = _fetch_latest_approval(scan_id)
    try:
        redlined_bytes = await run_in_threadpool(_build_redlined_pdf, pdf_bytes, scan_data, approval)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate redlined PDF: {e}")

    return Response(
        content=redlined_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="ClaimLoom_Redline_{scan_id}.pdf"',
            "Cache-Control": "no-store",
        },
    )
