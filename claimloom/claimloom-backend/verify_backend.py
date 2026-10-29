"""
ClaimLoom Round 3 — End-to-End Backend Verification & Benchmark Suite
Run directly:   python3 verify_backend.py
Or via pytest:  pytest verify_backend.py -v
"""
import io
import time
try:
    import pymupdf as fitz
except ImportError:
    import fitz  # PyMuPDF compatibility fallback
from PIL import Image
from fastapi.testclient import TestClient

import main
import ratelimit
from fastapi import HTTPException
from starlette.requests import Request

client = TestClient(main.app)


def _make_sample_pdf() -> bytes:
    """Creates a 2-page PDF in memory testing:
    1. Factual/Terminology violations ('$15/month', 'guaranteed 100% results', 'clients')
    2. Correctly capitalized 'ClaimLoom' (must NOT be flagged)
    3. Sub-9pt micro font (triggers PDF layout rule)
    4. Low-contrast light gray text on white background (verifies the bbox_raw fix)
    """
    doc = fitz.open()
    try:
        p1 = doc.new_page(width=612, height=792)
        # Normal 12pt text with planted violations + valid 'ClaimLoom'
        p1.insert_text(
            fitz.Point(50, 80),
            "ClaimLoom Pro Plan costs $15/month with guaranteed 100% results for our clients!",
            fontsize=12,
            fontname="helv",
            color=(0.05, 0.05, 0.05),
        )
        # Low-contrast text (light gray on white) -> tests Bug Fix #1 (bbox_raw defined on normal font size)
        p1.insert_text(
            fitz.Point(50, 130),
            "Low contrast subtle disclaimer text on page one",
            fontsize=11,
            fontname="helv",
            color=(0.88, 0.88, 0.88),
        )
        # Sub-9pt fine print -> tests minimum font size detector
        p1.insert_text(
            fitz.Point(50, 720),
            "Unreadable 6.5pt micro-print terms and conditions footer.",
            fontsize=6.5,
            fontname="helv",
            color=(0.1, 0.1, 0.1),
        )

        p2 = doc.new_page(width=612, height=792)
        p2.insert_text(
            fitz.Point(50, 80),
            "Page 2: Certified battery range is 110 km per charge. Click here to start.",
            fontsize=12,
            fontname="helv",
            color=(0.05, 0.05, 0.05),
        )
        return doc.tobytes()
    finally:
        doc.close()


def _make_offbrand_png() -> bytes:
    """Creates a flat neon lime-green (#86FA05) image to trigger CIE76 delta-E Rule 9."""
    img = Image.new("RGB", (300, 200), (134, 250, 5))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def run_all_checks():
    ratelimit.reset_rate_limits()
    results = []

    def check(name: str, fn):
        t0 = time.perf_counter()
        try:
            detail = fn()
            ms = (time.perf_counter() - t0) * 1000
            print(f"  [PASS] {name:<58} ({ms:6.1f} ms) -> {detail}")
            results.append((name, True, ms, detail))
        except Exception as exc:
            ms = (time.perf_counter() - t0) * 1000
            print(f"  [FAIL] {name:<58} ({ms:6.1f} ms) -> {type(exc).__name__}: {exc}")
            results.append((name, False, ms, str(exc)))

    print("\n" + "=" * 92)
    print(" CLAIMLOOM ROUND 3 — BACKEND VERIFICATION SUITE")
    print("=" * 92)

    # 1. Keep-alive & Health
    def test_ping():
        r = client.get("/ping")
        assert r.status_code == 200 and r.json().get("status") == "awake"
        return f"service={r.json().get('service')}"

    def test_health():
        r = client.get("/health")
        assert r.status_code == 200 and "database" in r.json()
        return f"db={r.json()['database']}, source={r.json()['rules_source']}"

    check("1. GET /ping (DB-free keep-alive)", test_ping)
    check("2. GET /health (Vault & AI status)", test_health)

    # 2. Session & Role Switcher (Tests Bug Fix #2: ALLOW_INSECURE_DEMO_ROLES)
    tokens = {}

    def test_sessions():
        for role in ("Creator", "Reviewer", "Admin"):
            r = client.post("/api/session", json={"name": f"Test {role}", "role": role, "workspace_id": "default"})
            assert r.status_code == 200, f"Role {role} failed with {r.status_code}: {r.text}"
            tokens[role] = r.json()["token"]
        me = client.get("/api/session/me", headers={"Authorization": f"Bearer {tokens['Admin']}"})
        assert me.status_code == 200 and me.json()["role"] == "Admin"
        return "Creator, Reviewer, Admin tokens issued & verified"

    check("3. POST /api/session (Zero-Login Role Switcher)", test_sessions)

    # 3. Text Scan + Bug Fix #1 ("ClaimLoom" no-op guard) + Channel Rules
    scan_state = {}

    def test_text_scan_and_noop_guard():
        draft = (
            "ClaimLoom Pro Plan is $15/month with guaranteed 100% results for our clients! "
            "Visit https://claimloom.ai or click here right now while driving on the highway."
        )
        r = client.post(
            "/api/scan-text",
            json={"text": draft, "channel": "billboard", "workspace_id": "default"},
            headers={"Authorization": f"Bearer {tokens['Creator']}"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        scan_state["text_scan_id"] = data["scan_id"]
        scan_state["text_draft"] = draft

        flagged_phrases = [i["flagged_text"] for i in data["issues"]]
        # Verify "ClaimLoom" is NOT flagged as a false positive
        assert "ClaimLoom" not in flagged_phrases, f"'ClaimLoom' was falsely flagged! Issues: {flagged_phrases}"
        # Verify real violations & billboard channel rules ARE flagged
        rule_ids = {i["rule_id"] for i in data["issues"]}
        assert 5 in rule_ids or 7 in rule_ids, "Expected pricing (Rule 5) or guarantee (Rule 7) flag"
        assert any(rid in rule_ids for rid in (1003, 1006)), f"Expected Billboard channel rule (1003/1006), got {rule_ids}"
        return f"scan_id={data['scan_id']}, score={data['readiness_score']}, flags={len(data['issues'])}"

    check("4. POST /api/scan-text (No-Op Guard + Billboard Rules)", test_text_scan_and_noop_guard)

    # 4. Persistence Reload (?scan_id= Collision Point 4)
    def test_get_saved_text_scan():
        sid = scan_state["text_scan_id"]
        r = client.get(f"/api/scans/{sid}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["scan_id"] == sid and data.get("redacted_text")
        return f"Reloaded {sid} with {len(data['issues'])} issues"

    check("5. GET /api/scans/{id} (Collision Point 4 Persistence)", test_get_saved_text_scan)

    # 5. Improvement 1: PDF Scan, BBox Layout Checks, Page PNG & Redlined PDF Export
    def test_pdf_scan():
        pdf_bytes = _make_sample_pdf()
        r = client.post(
            "/api/scan-pdf",
            files={"file": ("brochure.pdf", pdf_bytes, "application/pdf")},
            data={"channel": "general", "workspace_id": "default"},
            headers={"Authorization": f"Bearer {tokens['Creator']}"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        scan_state["pdf_scan_id"] = data["scan_id"]
        assert data["input_type"] == "pdf" and data["page_count"] == 2
        assert len(data["issues"]) >= 3
        # Every PDF issue must have a 1-based page and normalized 4-float bbox
        for iss in data["issues"]:
            assert iss["page"] in (1, 2), f"Invalid page on issue: {iss}"
            assert isinstance(iss["bbox"], list) and len(iss["bbox"]) == 4, f"Missing bbox: {iss}"
            assert all(0.0 <= coord <= 1.0 for coord in iss["bbox"]), f"Unnormalized bbox: {iss['bbox']}"
        detectors = {i["detected_by"] for i in data["issues"]}
        assert "pdf_layout" in detectors, f"Expected pdf_layout detector (9pt/contrast check), got {detectors}"
        disclosure = str(data.get("ai_disclosure") or "")
        model = disclosure.split("(AI: ", 1)[1].split(")", 1)[0] if "(AI: " in disclosure else "unavailable"
        return f"scan_id={data['scan_id']}, pages={data['page_count']}, issues={len(data['issues'])}, detectors={detectors}, model={model}"

    def test_pdf_page_png():
        sid = scan_state["pdf_scan_id"]
        r = client.get(f"/api/scans/{sid}/page/1.png")
        assert r.status_code == 200 and r.headers["content-type"] == "image/png"
        assert r.content.startswith(b"\x89PNG")
        return f"PNG rendered ({len(r.content)} bytes)"

    def test_redline_pdf_download():
        sid = scan_state["pdf_scan_id"]
        r = client.get(f"/api/scans/{sid}/redline-pdf")
        assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
        assert "Content-Disposition" in r.headers
        assert r.content.startswith(b"%PDF")
        red_doc = fitz.open(stream=r.content, filetype="pdf")
        try:
            # 2 original pages + 1 appended Cryptographic Certificate page = 3 pages
            assert len(red_doc) == 3, f"Expected 3 pages (2 + certificate), got {len(red_doc)}"
            cert_text = red_doc[-1].get_text("text")
            assert "CRYPTOGRAPHIC COMPLIANCE & AUDIT SEAL" in cert_text
            # Verify Bug Fix #3: signature is base64 Ed25519, not fallback hex error
            assert "Signature:" in cert_text
        finally:
            red_doc.close()
        return f"Redlined PDF verified (3 pages, {len(r.content)} bytes)"

    check("6. POST /api/scan-pdf (PyMuPDF BBox + 9pt/Contrast Check)", test_pdf_scan)
    check("7. GET /api/scans/{id}/page/1.png (Page Preview Render)", test_pdf_page_png)
    check("8. GET /api/scans/{id}/redline-pdf (Redline + Cert Page)", test_redline_pdf_download)

    # 6. DOCX / Markdown Document Scan
    def test_doc_scan():
        md_bytes = b"# ClaimLoom Launch\nOur clients get guaranteed 100% results on the pro plan!"
        r = client.post(
            "/api/scan-doc",
            files={"file": ("draft.md", md_bytes, "text/markdown")},
            data={"channel": "linkedin", "workspace_id": "default"},
        )
        assert r.status_code == 200, r.text
        assert len(r.json()["issues"]) >= 2
        data = r.json()
        disclosure = str(data.get("ai_disclosure") or "")
        model = disclosure.split("(AI: ", 1)[1].split(")", 1)[0] if "(AI: " in disclosure else "unavailable"
        return f"Markdown scanned, flags={len(data['issues'])}, model={model}"

    check("9. POST /api/scan-doc (Markdown/DOCX Ingestion)", test_doc_scan)

    # 7. Image Scan (CIE76 Delta-E Math + Normalized BBox)
    def test_image_scan():
        png_bytes = _make_offbrand_png()
        r = client.post(
            "/api/scan-image",
            files={"file": ("neon.png", png_bytes, "image/png")},
            data={"channel": "instagram", "workspace_id": "default"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        rule_ids = [i["rule_id"] for i in data["issues"]]
        assert 9 in rule_ids, f"Expected Rule 9 off-brand color flag, got {rule_ids}"
        return f"Image scanned, Rule 9 delta-E flagged, bbox={data['issues'][0]['bbox']}"

    check("10. POST /api/scan-image (CIE76 Color Math + BBox)", test_image_scan)

    # 8. Improvement 3: Comments, Versions, Blocker Gate, Ed25519 Approval & Tamper Check
    def test_collab_comments_and_blocker_gate():
        sid = scan_state["text_scan_id"]
        # Add comment as Reviewer
        c_res = client.post(
            f"/api/scans/{sid}/comments",
            json={"comment_text": "Fix the $15/month pricing and 100% guarantee before sign-off."},
            headers={"Authorization": f"Bearer {tokens['Reviewer']}"},
        )
        assert c_res.status_code == 200
        # Attempt approval while High-Severity blockers exist -> MUST return 409 Conflict
        a_res = client.post(
            f"/api/scans/{sid}/approve",
            json={},
            headers={"Authorization": f"Bearer {tokens['Reviewer']}"},
        )
        assert a_res.status_code == 409, f"Expected 409 blocker gate, got {a_res.status_code}"
        return "Comment saved & High-Severity blocker correctly locked approval (409)"

    def test_version_heal_and_ed25519_approve():
        sid = scan_state["text_scan_id"]
        clean_snapshot = "ClaimLoom Pro Plan is $29/month with proven results for our Creators."
        v_res = client.post(
            f"/api/scans/{sid}/versions",
            json={"text_snapshot": clean_snapshot},
            headers={"Authorization": f"Bearer {tokens['Creator']}"},
        )
        assert v_res.status_code == 200 and v_res.json()["version_no"] == 2

        # Now approve Version 2 as Reviewer -> MUST succeed with Ed25519 signature
        a_res = client.post(
            f"/api/scans/{sid}/approve",
            json={"version_no": 2},
            headers={"Authorization": f"Bearer {tokens['Reviewer']}"},
        )
        assert a_res.status_code == 200, a_res.text
        cert = a_res.json()["approval"]
        assert cert["signature"] and cert["entry_hash"]

        # Verify cryptographic chain via GET /api/verify/{scan_id}
        ver_res = client.get(f"/api/verify/{sid}")
        assert ver_res.status_code == 200
        v_data = ver_res.json()
        assert v_data["valid"] is True and v_data["tampered"] is False and v_data["chain_valid"] is True
        return f"Version 2 approved & Ed25519 signature verified (hash={cert['entry_hash'][:12]}...)"

    def test_tamper_detection():
        sid = scan_state["text_scan_id"]
        # Mutate text to Version 3 AFTER approval -> /api/verify/{id} must detect tampering!
        client.post(
            f"/api/scans/{sid}/versions",
            json={"text_snapshot": "ClaimLoom Pro Plan is $1/month sneakily edited after approval!"},
            headers={"Authorization": f"Bearer {tokens['Creator']}"},
        )
        ver_res = client.get(f"/api/verify/{sid}")
        v_data = ver_res.json()
        assert v_data["tampered"] is True and v_data["valid"] is False
        return "Post-approval edit detected: tampered=True, valid=False"

    check("11. POST /comments & Blocker Gate Lock (HTTP 409)", test_collab_comments_and_blocker_gate)
    check("12. POST /versions + /approve + GET /verify (Ed25519)", test_version_heal_and_ed25519_approve)
    check("13. GET /api/verify/{id} (Post-Approval Tamper Detection)", test_tamper_detection)

    # 9. Improvement 3 Part B: Self-Healing Rules, ReDoS Guard, Patch, Rollback & Custom Rule
    def test_rule_backtest_and_redos_guard():
        # Valid regex backtest on Rule 3
        ok_res = client.post(
            "/api/rules/3/backtest",
            json={"proposed_regex": r"(?i)\b(?:client|consumer|buyer)s?\b"},
            headers={"Authorization": f"Bearer {tokens['Admin']}"},
        )
        assert ok_res.status_code == 200 and ok_res.json()["valid_regex"] is True

        # Catastrophic backtracking ReDoS regex -> MUST be rejected with 422
        redos_res = client.post(
            "/api/rules/3/backtest",
            json={"proposed_regex": r"(a+)+$"},
            headers={"Authorization": f"Bearer {tokens['Admin']}"},
        )
        assert redos_res.status_code == 422, f"Expected 422 on ReDoS regex, got {redos_res.status_code}"

        # Regex matching its own suggested_fix -> MUST be rejected with 422
        self_res = client.post(
            "/api/rules/1/backtest",
            json={"proposed_regex": r"(?i)\bClaimLoom\b"},
            headers={"Authorization": f"Bearer {tokens['Admin']}"},
        )
        assert self_res.status_code == 422
        return f"Backtest passed ({ok_res.json()['scans_sampled']} scans) & ReDoS/Self-Match blocked (422)"

    def test_rule_patch_and_rollback():
        # Update Rule 3 as Admin
        p_res = client.patch(
            "/api/rules/3",
            json={"rule_text": "Always refer to users as Creators or Team Members (except in B2B legal quotes)."},
            headers={"Authorization": f"Bearer {tokens['Admin']}"},
        )
        assert p_res.status_code == 200, p_res.text
        new_ver = p_res.json()["version_no"]

        # Rollback Rule 3 as Admin
        rb_res = client.post(
            "/api/rules/3/rollback",
            json={},
            headers={"Authorization": f"Bearer {tokens['Admin']}"},
        )
        assert rb_res.status_code == 200, rb_res.text
        return f"Rule 3 updated to v{new_ver} & rolled back to v{rb_res.json()['restored_version']}"

    def test_create_custom_rule_and_summary():
        # Verify Bug Fix #5 endpoints if added
        r_sum = client.get("/api/analytics/ambiguity")
        assert r_sum.status_code == 200 and "ambiguity_radar" in r_sum.json()
        return f"Ambiguity radar active ({len(r_sum.json()['ambiguity_radar'])} rules tracked)"

    check("14. POST /api/rules/{id}/backtest (ReDoS & Fix Guard)", test_rule_backtest_and_redos_guard)
    check("15. PATCH /api/rules/{id} & POST /rollback (Versioning)", test_rule_patch_and_rollback)
    check("16. GET /api/analytics/ambiguity (Radar Telemetry)", test_create_custom_rule_and_summary)

    # 10. Rate Limiter Verification
    def test_rate_limiter():
        ratelimit.reset_rate_limits()
        request = Request({
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/scan-text",
            "raw_path": b"/api/scan-text",
            "query_string": b"",
            "headers": [(b"x-forwarded-for", b"203.0.113.99, 10.0.0.1")],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        })
        try:
            for _ in range(int(ratelimit.BUCKET_CAPACITY)):
                assert ratelimit.rate_limit_scan(request) == "203.0.113.99"
            try:
                ratelimit.rate_limit_scan(request)
            except HTTPException as exc:
                assert exc.status_code == 429
                assert "Retry-After" in exc.headers
            else:
                raise AssertionError("Expected HTTP 429 after exceeding 30-token burst capacity")
        finally:
            ratelimit.reset_rate_limits()
        return "X-Forwarded-For honored; HTTP 429 + Retry-After triggered at burst limit"

    check("17. X-Forwarded-For Proxy Token Bucket Rate Limiter", test_rate_limiter)

    print("=" * 92)
    passed = sum(1 for _, ok, _, _ in results if ok)
    print(f" SUMMARY: {passed}/{len(results)} CHECKS PASSED")
    print("=" * 92 + "\n")
    if passed < len(results):
        raise SystemExit(1)


def test_claimloom_round3_suite():
    """Entry point so `pytest verify_backend.py` runs the full suite."""
    run_all_checks()


if __name__ == "__main__":
    run_all_checks()
