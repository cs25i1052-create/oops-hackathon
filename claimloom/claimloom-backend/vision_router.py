"""POST /api/scan-image (Round 3 Upgrade)
 - Colors, palette distance (CIE76 delta-E) and WCAG contrast are MEASURED with exact math (Pillow), never guessed by AI.
 - Text inside the image is read by an AI vision model (OCR) with normalized bounding boxes [x0, y0, x1, y1] (0.0..1.0)
   and audited by the Two-Tier + Hybrid RAG text pipeline.
 - Supports Collision Point 3 multipart form fields (`file`, `channel`, `workspace_id`) and Collision Point 4 persistence."""
import io
import hashlib
import math
from typing import Any, Dict, List, Optional, Tuple

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.concurrency import run_in_threadpool
from PIL import Image, ImageOps

import ai_client
import cache
import db
import pipeline
from rule_version import get_rules_version
from ratelimit import rate_limit_scan
from schemas import (
    EvidenceCitation,
    IssueItem,
    ReauditInfo,
    Region,
    ScanResponse,
    new_scan_id,
    normalize_channel,
    score_issues,
)
from seed_db import RULES_DATA
from session import SessionUser, get_current_session, resolve_workspace_id

router = APIRouter()

MAX_BYTES = 8 * 1024 * 1024
APPROVED_BRAND_HEX = {
    "#1E3A8A": (30, 58, 138),    # Indium Blue
    "#FF5500": (255, 85, 0),     # Stark Orange
    "#FFFFFF": (255, 255, 255),  # White
    "#0F172A": (15, 23, 42),     # Slate
}
DELTA_E_LIMIT = 25.0      # CIE76 delta-E above ~25 is clearly a different color
GRAPHIC_COVERAGE = 0.75   # contrast is only judged when 2 colors make up most of the image (flat graphic, not a photo)


# ------------------------------------------------------------------ exact color math
def rgb_to_hex(rgb) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _srgb_to_linear(c: float) -> float:
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def rgb_to_lab(rgb) -> Tuple[float, float, float]:
    r, g, b = (_srgb_to_linear(v) for v in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = (0.2126 * r + 0.7152 * g + 0.0722 * b)
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda t: t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def delta_e76(rgb1, rgb2) -> float:
    l1, l2 = rgb_to_lab(rgb1), rgb_to_lab(rgb2)
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(l1, l2)))


def relative_luminance(rgb) -> float:
    def channel(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def wcag_contrast_ratio(rgb1, rgb2) -> float:
    l1, l2 = relative_luminance(rgb1), relative_luminance(rgb2)
    return round((max(l1, l2) + 0.05) / (min(l1, l2) + 0.05), 2)


# ------------------------------------------------------------------ helpers
def _clamp01(v: float) -> float:
    return round(min(max(float(v), 0.0), 1.0), 4)


def _normalize_bbox_coords(raw_bbox: Any, img_w: int, img_h: int) -> Optional[List[float]]:
    """Normalizes a 4-element bbox from 0..1, 0..1000, or pixel coordinates into [x0, y0, x1, y1] in 0.0..1.0."""
    if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) != 4:
        return None
    try:
        vals = [float(x) for x in raw_bbox]
    except (TypeError, ValueError):
        return None

    max_v = max(vals)
    if max_v <= 1.05:
        x0, y0, x1, y1 = vals
    elif max_v <= 1000.0 and (img_w > 1000 or img_h > 1000 or max_v > max(img_w, img_h)):
        x0, y0, x1, y1 = [v / 1000.0 for v in vals]
    else:
        x0 = vals[0] / max(img_w, 1)
        y0 = vals[1] / max(img_h, 1)
        x1 = vals[2] / max(img_w, 1)
        y1 = vals[3] / max(img_h, 1)

    x0, x1 = min(x0, x1), max(x0, x1)
    y0, y1 = min(y0, y1), max(y0, y1)
    if x1 - x0 < 0.02:
        x1 = min(1.0, x0 + 0.15)
    if y1 - y0 < 0.02:
        y1 = min(1.0, y0 + 0.06)
    return [_clamp01(x0), _clamp01(y0), _clamp01(x1), _clamp01(y1)]


def _rule(rule_id: int) -> dict:
    rule = db.rules_by_id().get(rule_id)
    if rule:
        return rule
    return next(r for r in RULES_DATA if r["rule_id"] == rule_id)


def _load_flat_rgb(contents: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(contents))
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):  # transparent areas must become WHITE, not black
        img = img.convert("RGBA")
        background = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(background, img)
    return img.convert("RGB")


def _dominant_colors(img: Image.Image):
    small = img.resize((150, 150))
    q = small.quantize(colors=4, dither=Image.Dither.NONE)
    palette = q.getpalette()
    total = 150 * 150
    colors = []
    for count, idx in sorted(q.getcolors(), reverse=True):
        colors.append((tuple(palette[idx * 3: idx * 3 + 3]), count / total))
    return colors  # [(rgb, share), ...] biggest first


def _issue(
    rule_id: int,
    flagged: str,
    explanation: str,
    fix: str,
    confidence: float,
    region: Optional[Region] = None,
    bbox: Optional[List[float]] = None,
    channel: str = "general",
) -> IssueItem:
    rule = _rule(rule_id)
    return IssueItem(
        id="",
        severity=rule["severity"],
        violation_type=rule["violation_type"],
        flagged_text=flagged,
        start=-1,
        end=-1,
        region=region,
        rule_id=rule_id,
        rule_cited=rule["rule_cited"],
        source_ref=rule["source_ref"],
        explanation=explanation,
        suggested_fix=fix,
        confidence=confidence,
        detected_by="rule_engine",
        claim_status=None,
        page=1,
        bbox=bbox,
        channel=channel,
    )


def _measure(img: Image.Image, channel: str = "general") -> Tuple[List[IssueItem], list]:
    issues: List[IssueItem] = []
    colors = _dominant_colors(img)
    full = Region(x=0, y=0, w=img.width, h=img.height)

    # 1) palette check on the main colors
    for idx, (rgb, share) in enumerate(colors[:2]):
        if share < 0.25:
            continue
        nearest = min(APPROVED_BRAND_HEX, key=lambda k: delta_e76(rgb, APPROVED_BRAND_HEX[k]))
        de = delta_e76(rgb, APPROVED_BRAND_HEX[nearest])
        if de > DELTA_E_LIMIT:
            hex_ = rgb_to_hex(rgb)
            # Normalized bounding box for Rohit's canvas
            norm_box = [0.02, 0.02, 0.98, 0.98] if idx == 0 else [0.06, 0.06, 0.94, 0.94]
            issues.append(
                _issue(
                    9,
                    f"Dominant color {hex_} ({int(share * 100)}% of image)",
                    f"{hex_} is not in the approved palette. Closest brand color is {nearest} (delta-E {de:.0f}, limit {DELTA_E_LIMIT:.0f}).",
                    f"Replace {hex_} with the approved brand color {nearest}",
                    0.9,
                    region=full,
                    bbox=norm_box,
                    channel=channel,
                )
            )

    # 2) contrast check, only for flat graphics where the top-2 colors are really background + text
    if len(colors) >= 2 and colors[0][1] + colors[1][1] >= GRAPHIC_COVERAGE:
        bg, fg = colors[0][0], colors[1][0]
        ratio = wcag_contrast_ratio(bg, fg)
        if ratio < 4.5:
            candidates = {h: c for h, c in APPROVED_BRAND_HEX.items() if c != bg}
            best_hex = max(candidates, key=lambda h: wcag_contrast_ratio(candidates[h], bg))
            best_ratio = wcag_contrast_ratio(candidates[best_hex], bg)
            issues.append(
                _issue(
                    10,
                    f"Possible low contrast {ratio}:1 ({rgb_to_hex(fg)} on {rgb_to_hex(bg)})",
                    f"The two main colors measure {ratio}:1, below the WCAG 2.1 AA minimum of 4.5:1. "
                    "This is an estimate from the image's dominant colors, so please verify the actual text.",
                    f"Use {best_hex} text on {rgb_to_hex(bg)} ({best_ratio}:1 contrast)",
                    0.6,
                    region=None,
                    bbox=[0.10, 0.20, 0.90, 0.80],
                    channel=channel,
                )
            )
    return issues, colors


def _read_text_and_boxes_with_ai(img: Image.Image) -> Tuple[str, List[Dict[str, Any]]]:
    """AI vision reads the visible text AND returns normalized [x0, y0, x1, y1] bounding boxes per text line."""
    thumb = img.copy()
    thumb.thumbnail((1280, 1280))
    buf = io.BytesIO()
    thumb.save(buf, format="JPEG", quality=85)
    data, _label = ai_client.complete_json(
        "You read text and bounding boxes from marketing images. Reply with ONE JSON object: "
        '{"text": "all visible text in reading order, one line per block", '
        '"blocks": [{"text": "exact line text", "bbox": [x0, y0, x1, y1]}]} '
        "where bbox coordinates are normalized 0.0 to 1.0 fractions of image width and height ([left, top, right, bottom]). "
        "If there is no text, return empty text and empty blocks. Do not describe the image.",
        "Transcribe all visible text and their normalized [x0, y0, x1, y1] bounding boxes in this image.",
        image=(buf.getvalue(), "image/jpeg"),
        max_tokens=1800,
    )
    if not isinstance(data, dict):
        return "", []
    text = str(data.get("text") or "")[:4000]
    raw_blocks = data.get("blocks") if isinstance(data.get("blocks"), list) else []
    clean_blocks: List[Dict[str, Any]] = []
    for b in raw_blocks:
        if isinstance(b, dict) and b.get("text"):
            norm_b = _normalize_bbox_coords(b.get("bbox"), thumb.width, thumb.height)
            if norm_b:
                clean_blocks.append({"text": str(b["text"]).strip(), "bbox": norm_b})
    if not text and clean_blocks:
        text = "\n".join(b["text"] for b in clean_blocks)
    return text, clean_blocks


def _match_issue_bbox_in_image(
    flagged_text: str,
    blocks: List[Dict[str, Any]],
    ocr_lines: List[str],
    fallback_idx: int,
) -> List[float]:
    """Finds the best normalized [x0, y0, x1, y1] box for `flagged_text` from Vision OCR blocks or line index."""
    needle = (flagged_text or "").strip().lower()
    if needle:
        for blk in blocks:
            hay = blk["text"].lower()
            if needle in hay or hay in needle:
                return blk["bbox"]
        # Try matching any 2+ word phrase
        words = needle.split()
        if len(words) >= 2:
            sub = " ".join(words[:2])
            for blk in blocks:
                if sub in blk["text"].lower():
                    return blk["bbox"]

        # Fallback to line position within ocr_lines
        total_lines = max(len(ocr_lines), 1)
        for line_i, line_str in enumerate(ocr_lines):
            if needle in line_str.lower():
                y0 = _clamp01(0.12 + (line_i / total_lines) * 0.72)
                y1 = _clamp01(min(0.95, y0 + max(0.08, 0.65 / total_lines)))
                return [0.08, y0, 0.92, y1]

    # Deterministic non-overlapping band fallback
    y0 = _clamp01(0.14 + ((fallback_idx % 7) * 0.10))
    return [0.10, y0, 0.90, _clamp01(y0 + 0.08)]


def analyze_image(
    contents: bytes,
    channel: str = "general",
    workspace_id: str = "default",
):
    norm_ch = normalize_channel(channel)
    norm_ws = (workspace_id or "default").strip() or "default"

    img = _load_flat_rgb(contents)
    issues, colors = _measure(img, channel=norm_ch)
    ai_ok, label, pii = True, "", 0
    redacted_text = ""
    verified_claims: List[EvidenceCitation] = []
    rag_results: Dict[str, Any] = {}
    kb_version = pipeline.get_kb_version(norm_ws)
    rules, _facts, _src = db.get_vault()
    rules_version = get_rules_version()

    try:
        ocr_text, ocr_blocks = "", []
        if not colors or len(colors) == 1 or colors[0][1] >= 0.995:
            label = "vision OCR skipped (uniform solid color)"
        else:
            ocr_text, ocr_blocks = _read_text_and_boxes_with_ai(img)
        if ocr_text.strip():
            ocr_lines = [ln.strip() for ln in ocr_text.splitlines() if ln.strip()]
            analysis = pipeline.analyze_text(
                ocr_text,
                with_positions=True,
                channel=norm_ch,
                workspace_id=norm_ws,
            )
            for idx, i in enumerate(analysis.issues):
                i.explanation = "In the image text: " + i.explanation
                # OCR text exists only inside the image; its character offsets do
                # not point into the user's editable text field.
                i.start = -1
                i.end = -1
                i.page = 1
                if not i.bbox:
                    i.bbox = _match_issue_bbox_in_image(i.flagged_text, ocr_blocks, ocr_lines, idx)
                if not i.region and i.bbox:
                    i.region = Region(
                        x=int(i.bbox[0] * img.width),
                        y=int(i.bbox[1] * img.height),
                        w=max(10, int((i.bbox[2] - i.bbox[0]) * img.width)),
                        h=max(10, int((i.bbox[3] - i.bbox[1]) * img.height)),
                    )
            issues.extend(analysis.issues)
            ai_ok = analysis.ai_ok
            label = analysis.model_label
            pii = analysis.pii_count
            redacted_text = analysis.redacted_text
            verified_claims = analysis.verified_claims
            rag_results = analysis.rag_results
            kb_version = analysis.kb_version
            rules_version = analysis.rules_version
        else:
            label = "vision OCR (no text found)"
    except ai_client.AIUnavailable as e:
        ai_ok, label = False, "none"
        print(f"[vision] OCR unavailable: {e}")
    except Exception as e:
        ai_ok, label = False, "none"
        print(f"[vision] OCR error: {e}")

    for n, i in enumerate(issues, 1):
        i.id = f"iss_img_{n}"

    return (
        issues,
        ai_ok,
        label,
        pii,
        redacted_text,
        verified_claims,
        rag_results,
        kb_version,
        rules_version,
    )


# ------------------------------------------------------------------ endpoint
@router.post("/api/scan-image", response_model=ScanResponse)
async def scan_image(
    background: BackgroundTasks,
    file: UploadFile = File(...),          # Collision Point 3: exact key "file"
    channel: str = Form("general"),        # Optional form field
    workspace_id: str = Form("default"),   # Optional form field
    _client_ip: str = Depends(rate_limit_scan),
    session: SessionUser = Depends(get_current_session),
):
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please upload an image file (PNG, JPG or WebP).")
    contents = await file.read()
    if len(contents) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Image is too large (max 8 MB).")

    norm_ch = normalize_channel(channel)
    norm_ws = resolve_workspace_id(workspace_id, session)

    image_hash = hashlib.sha256(contents).hexdigest()
    rules_version = get_rules_version()
    kb_version = pipeline.get_kb_version(norm_ws)
    cache_key = cache.make_cache_key(
        text=f"image_sha256:{image_hash}",
        channel=norm_ch,
        workspace_id=norm_ws,
        rules_version=rules_version,
        kb_version=kb_version,
    )
    cached_hit = cache.get_cached_scan(cache_key)
    if cached_hit:
        cached_hit["scan_id"] = new_scan_id()
        cached_hit["cached"] = True
        cached_hit["input_type"] = "image"
        cached_hit["channel"] = norm_ch
        cached_hit["workspace_id"] = norm_ws
        cached_response = ScanResponse(**cached_hit)
        payload = cached_response.model_dump()
        try:
            import main
            # Fix 2: also convert image to PDF on cached hits
            try:
                _img_pdf_buf = io.BytesIO()
                _load_flat_rgb(contents).save(_img_pdf_buf, format="PDF", resolution=100.0)
                _img_pdf_bytes_cached = _img_pdf_buf.getvalue()
            except Exception:
                _img_pdf_bytes_cached = None
            try:
                import pdf_engine as _pdf_engine_cached
                if _img_pdf_bytes_cached:
                    _pdf_engine_cached._remember_pdf_in_memory(cached_response.scan_id, image_hash, _img_pdf_bytes_cached, payload)
            except Exception:
                pass
            background.add_task(
                main.save_scan_persistence,
                payload,
                cached_response.redacted_text or "",
                "image",
                _img_pdf_bytes_cached,
                image_hash,
                session.name,
                None,
            )
        except Exception:
            background.add_task(
                db.save_scan,
                cached_response.scan_id,
                cached_response.readiness_score,
                cached_response.status,
                "image",
                payload,
            )
        return cached_response

    try:
        (
            issues,
            ai_ok,
            label,
            pii,
            redacted_text,
            verified_claims,
            rag_results,
            kb_version,
            rules_version,
        ) = await run_in_threadpool(analyze_image, contents, norm_ch, norm_ws)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or unreadable image file.")

    score, pillars, status = score_issues(issues, ai_ok=ai_ok)
    scan_id = new_scan_id()
    extra = "Colors, palette distance (CIE76 delta-E) and WCAG contrast are measured with exact math; text & bounding boxes in the image are read by AI."

    response_obj = ScanResponse(
        scan_id=scan_id,
        readiness_score=score,
        status=status,
        ai_status="ok" if ai_ok else "degraded",
        pillar_scores=pillars,
        ai_disclosure=pipeline.disclosure(label, ai_ok, extra)
        if ai_ok
        else "AI vision was unavailable, so text inside the image was NOT checked. " + extra,
        pii_redacted_count=pii,
        issues=issues,
        input_type="image",
        redacted_text=redacted_text,
        cached=False,
        channel=norm_ch,
        workspace_id=norm_ws,
        kb_version=kb_version,
        rules_version=rules_version,
        page_count=1,
        verified_claims=verified_claims,
        reaudit=ReauditInfo(needed=False, note=None),
    )

    resp_dict = response_obj.model_dump()
    if response_obj.ai_status == "ok":
        background.add_task(cache.set_cached_scan, cache_key, resp_dict)

    # Fix 2: Convert uploaded image to a single-page PDF so canvas
    # previews (GET /api/scans/{id}/page/1.png) and redline-pdf work for images.
    try:
        img_pdf_buf = io.BytesIO()
        _load_flat_rgb(contents).save(img_pdf_buf, format="PDF", resolution=100.0)
        img_pdf_bytes = img_pdf_buf.getvalue()
    except Exception:
        img_pdf_bytes = None

    try:
        import main
        import pdf_engine as _pdf_engine
        if img_pdf_bytes:
            _pdf_engine._remember_pdf_in_memory(scan_id, image_hash, img_pdf_bytes, resp_dict)
        background.add_task(
            main.save_scan_persistence,
            resp_dict,
            redacted_text,
            "image",
            img_pdf_bytes,
            image_hash,
            session.name,
            rag_results,
        )
    except Exception:
        background.add_task(
            db.save_scan,
            scan_id,
            score,
            status,
            "image",
            {"issues": [i.model_dump() for i in issues], "ai_ok": ai_ok},
        )

    return response_obj
