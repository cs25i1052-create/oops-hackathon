"""POST /api/scan-image
 - Colors, palette distance (CIE76 delta-E) and WCAG contrast are MEASURED with exact math (Pillow), never guessed by AI.
 - Text inside the image is read by an AI vision model (OCR) and then checked by the SAME text pipeline.
   If no vision model is available the image checks still run and the response is marked ai_status="degraded"."""
import io
import math
from typing import List, Tuple

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image, ImageOps

import ai_client
import db
import pipeline
from schemas import IssueItem, Region, ScanResponse, new_scan_id, score_issues
from seed_db import RULES_DATA

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
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
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
def _rule(rule_id: int) -> dict:
    rule = db.rules_by_id().get(rule_id)
    if rule:
        return rule
    return next(r for r in RULES_DATA if r["rule_id"] == rule_id)  # Neon not seeded with it yet


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


def _issue(rule_id: int, flagged: str, explanation: str, fix: str, confidence: float, region=None) -> IssueItem:
    rule = _rule(rule_id)
    return IssueItem(
        id="", severity=rule["severity"], violation_type=rule["violation_type"],
        flagged_text=flagged, start=-1, end=-1, region=region,
        rule_id=rule_id, rule_cited=rule["rule_cited"], source_ref=rule["source_ref"],
        explanation=explanation, suggested_fix=fix, confidence=confidence, detected_by="rule_engine",
        claim_status=None,
    )


def _measure(img: Image.Image) -> List[IssueItem]:
    issues: List[IssueItem] = []
    colors = _dominant_colors(img)
    full = Region(x=0, y=0, w=img.width, h=img.height)

    # 1) palette check on the main colors
    for rgb, share in colors[:2]:
        if share < 0.25:
            continue
        nearest = min(APPROVED_BRAND_HEX, key=lambda k: delta_e76(rgb, APPROVED_BRAND_HEX[k]))
        de = delta_e76(rgb, APPROVED_BRAND_HEX[nearest])
        if de > DELTA_E_LIMIT:
            hex_ = rgb_to_hex(rgb)
            issues.append(_issue(
                9, f"Dominant color {hex_} ({int(share * 100)}% of image)",
                f"{hex_} is not in the approved palette. Closest brand color is {nearest} (delta-E {de:.0f}, limit {DELTA_E_LIMIT:.0f}).",
                f"Replace {hex_} with the approved brand color {nearest}", 0.9, full))

    # 2) contrast check, only for flat graphics where the top-2 colors are really background + text
    if len(colors) >= 2 and colors[0][1] + colors[1][1] >= GRAPHIC_COVERAGE:
        bg, fg = colors[0][0], colors[1][0]
        ratio = wcag_contrast_ratio(bg, fg)
        if ratio < 4.5:
            candidates = {h: c for h, c in APPROVED_BRAND_HEX.items() if c != bg}
            best_hex = max(candidates, key=lambda h: wcag_contrast_ratio(candidates[h], bg))
            best_ratio = wcag_contrast_ratio(candidates[best_hex], bg)
            issues.append(_issue(
                10, f"Possible low contrast {ratio}:1 ({rgb_to_hex(fg)} on {rgb_to_hex(bg)})",
                f"The two main colors measure {ratio}:1, below the WCAG 2.1 AA minimum of 4.5:1. "
                "This is an estimate from the image's dominant colors, so please verify the actual text.",
                f"Use {best_hex} text on {rgb_to_hex(bg)} ({best_ratio}:1 contrast)", 0.6, None))
    return issues


def _read_text_with_ai(img: Image.Image) -> str:
    """AI vision reads the words in the image. Raises AIUnavailable if no vision model works."""
    thumb = img.copy()
    thumb.thumbnail((1280, 1280))
    buf = io.BytesIO()
    thumb.save(buf, format="JPEG", quality=85)
    data, _label = ai_client.complete_json(
        'You read text from images. Reply with ONE JSON object: {"text": "all visible text, in reading order, one line per text block"}. '
        "If there is no text, use an empty string. Do not describe the image.",
        "Transcribe all visible text in this image.",
        image=(buf.getvalue(), "image/jpeg"),
        max_tokens=1500,
    )
    return str(data.get("text", ""))[:4000] if isinstance(data, dict) else ""


def analyze_image(contents: bytes):
    img = _load_flat_rgb(contents)
    issues = _measure(img)
    ai_ok, label, pii = True, "", 0
    try:
        ocr_text = _read_text_with_ai(img)
        if ocr_text.strip():
            analysis = pipeline.analyze_text(ocr_text, with_positions=False)
            for i in analysis.issues:
                i.explanation = "In the image text: " + i.explanation
            issues.extend(analysis.issues)
            ai_ok, label, pii = analysis.ai_ok, analysis.model_label, analysis.pii_count
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
    return issues, ai_ok, label, pii


# ------------------------------------------------------------------ endpoint
@router.post("/api/scan-image", response_model=ScanResponse)
async def scan_image(background: BackgroundTasks, file: UploadFile = File(...)):
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please upload an image file (PNG, JPG or WebP).")
    contents = await file.read()
    if len(contents) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Image is too large (max 8 MB).")
    try:
        issues, ai_ok, label, pii = await run_in_threadpool(analyze_image, contents)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or unreadable image file.")

    score, pillars, status = score_issues(issues, ai_ok=ai_ok)
    scan_id = new_scan_id()
    background.add_task(db.save_scan, scan_id, score, status, "image",
                        {"issues": [i.model_dump() for i in issues], "ai_ok": ai_ok})
    extra = "Colors, palette distance (CIE76 delta-E) and WCAG contrast are measured with exact math; text in the image is read by AI."
    return ScanResponse(
        scan_id=scan_id, readiness_score=score, status=status,
        ai_status="ok" if ai_ok else "degraded", pillar_scores=pillars,
        ai_disclosure=pipeline.disclosure(label, ai_ok, extra) if ai_ok else
        "AI vision was unavailable, so text inside the image was NOT checked. " + extra,
        pii_redacted_count=pii, issues=issues,
    )
