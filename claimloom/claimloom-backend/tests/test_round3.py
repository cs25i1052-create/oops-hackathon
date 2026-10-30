import sys
import os
# Force Python to look in the main backend directory for your modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from fastapi.testclient import TestClient
import main
import ai_client
import collab_router
import db
import pipeline
import pdf_engine
from rag_verifier import extract_numbers_with_units, verify_claims, get_kb_version
from db import get_db_connection

# --- 1. RAG & DATABASE TESTS (These will pass immediately) ---
import pytest
from rag_verifier import extract_numbers_with_units, verify_claims, get_kb_version
from db import get_db_connection

def test_number_extraction():
    """Validates the deterministic regex unit extraction."""
    text = "The Pro Plan is $29/month and gets 110 km range in 45 minutes."
    nums = extract_numbers_with_units(text)
    assert "110km" in nums
    assert "$29/month" in nums
    assert "45minutes" in nums

def test_rag_verified_claim():
    """Tests if a valid factual claim correctly retrieves the KB chunk and verifies it."""
    result = verify_claims("Our certified battery range is 110 km under standard conditions.")
    assert len(result["verified_claims"]) > 0
    assert result["verified_claims"][0]["verdict"] == "Verified"
    assert result["verified_claims"][0]["similarity"] >= 0.72

def test_rag_contradicted_claim():
    """Tests if an invalid quantitative claim flags a High-Severity contradiction."""
    result = verify_claims("The ClaimLoom Pro Plan costs $15/month.")
    assert len(result["contradicted_issues"]) > 0
    issue = result["contradicted_issues"][0]
    assert issue["severity"] == "High"
    assert issue["claim_status"] == "Contradicted Fact"
    assert issue["evidence"]["verdict"] == "Contradicted"

def test_kb_versioning():
    """Validates the cache invalidation version fetcher."""
    version = get_kb_version("default")
    assert isinstance(version, int)
    assert version >= 1

@pytest.mark.parametrize("endpoint, expected_status", [
    ("/ping", 200),
    ("/health", 200),
])
def test_system_health(endpoint, expected_status):
    """The keep-alive and diagnostics routes return their documented contracts."""
    with TestClient(main.app) as client:
        response = client.get(endpoint)
    assert response.status_code == expected_status
    body = response.json()
    assert body.get("status") == "awake"
    if endpoint == "/ping":
        assert body.get("service") == "claimloom-backend-v3"
    else:
        assert "database" in body
        assert "ai_providers_configured" in body

@pytest.mark.parametrize("channel, input_text, expected_flag", [
    ("billboard", "This is way too much text for a billboard because it exceeds the twelve word maximum limit easily.", True),
    ("linkedin", "DM me to get the product update.", True),
    ("general", "Standard professional text goes here.", False),
])
def test_channel_rules(channel, input_text, expected_flag, monkeypatch):
    """Validates channel-specific constraints."""
    monkeypatch.setattr(ai_client, "AI_MODE", "rules_only")
    with TestClient(main.app) as client:
        response = client.post("/api/scan-text", json={"text": input_text, "channel": channel})
    assert response.status_code == 200, response.text
    data = response.json()
    channel_issues = [issue for issue in data["issues"] if issue.get("channel") == channel and issue.get("rule_id", 0) >= 1000]
    assert bool(channel_issues) is expected_flag

def test_ed25519_tamper_signature(monkeypatch):
    """A valid approval verifies, and a modified Ed25519 signature is rejected."""
    monkeypatch.setenv("ALLOW_INSECURE_DEMO_ROLES", "true")
    monkeypatch.delenv("SESSION_ISSUER_SECRET", raising=False)
    monkeypatch.setattr(ai_client, "AI_MODE", "rules_only")
    with TestClient(main.app) as client:
        session = client.post("/api/session", json={"name": "Round 3 Reviewer", "role": "Reviewer", "workspace_id": "default"})
        assert session.status_code == 200, session.text
        headers = {"Authorization": f"Bearer {session.json()['token']}"}
        scan = client.post("/api/scan-text", json={"text": "Clear product information for enterprise teams."})
        assert scan.status_code == 200, scan.text
        scan_id = scan.json()["scan_id"]

        approved = client.post(f"/api/scans/{scan_id}/approve", json={}, headers=headers)
        assert approved.status_code == 200, approved.text
        assert approved.json()["approval"]["signature"]
        valid = client.get(f"/api/verify/{scan_id}")
        assert valid.status_code == 200, valid.text
        assert valid.json()["valid"] is True
        assert valid.json()["chain_valid"] is True

        approval = next(row for row in collab_router._approvals if row["scan_id"] == scan_id)
        original_signature = approval["signature"]
        try:
            approval["signature"] = "AAAA"
            tampered = client.get(f"/api/verify/{scan_id}")
            assert tampered.status_code == 200, tampered.text
            assert tampered.json()["valid"] is False
            assert tampered.json()["chain_valid"] is False
        finally:
            approval["signature"] = original_signature


def test_live_sample_pdf_scan_has_renderable_pages(monkeypatch):
    """The built-in brochure uses the real PDF pipeline and retains its bytes for previews."""
    monkeypatch.setattr(ai_client, "AI_MODE", "rules_only")
    with TestClient(main.app) as client:
        response = client.post(
            "/api/scan-sample-pdf",
            data={"channel": "general", "workspace_id": "default"},
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["input_type"] == "pdf"
        assert result["page_count"] == 2
        assert any(issue.get("detected_by") == "pdf_layout" for issue in result["issues"])
        preview = client.get(f"/api/scans/{result['scan_id']}/page/1.png")
        assert preview.status_code == 200
        assert preview.content.startswith(b"\x89PNG")
        redline = client.get(f"/api/scans/{result['scan_id']}/redline-pdf")
        assert redline.status_code == 200
        assert redline.content.startswith(b"%PDF")


def test_reset_demo_seeds_local_price_reaudit_scans(monkeypatch):
    """Demo reset works without Neon and seeds the two scans cited to price chunk 3."""
    monkeypatch.setattr(db, "_connect", lambda: None)
    with TestClient(main.app) as client:
        response = client.post("/api/admin/reset-demo")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "reset"
    assert main._mem_scans["demo_scan_1"]["status"] == "approved"
    assert main._mem_scans["demo_scan_2"]["status"] == "approved"
    affected = pipeline.reaudit_changed([3])
    assert {"demo_scan_1", "demo_scan_2"}.issubset(set(affected))
    assert main._mem_scans["demo_scan_1"]["status"] == "needs_reaudit"
    assert pdf_engine._mem_scan_json["demo_scan_2"]["reaudit"]["needed"] is True


def test_chunk3_price_update_syncs_rule5(monkeypatch):
    """Updating chunk 3 to $39/month must update Rule #5 so that:
    - Scanning 'The Pro Plan costs $39/month.' → zero Rule 5 violations.
    - Scanning 'The Pro Plan costs $29/month.' → Rule 5 flagged.
    After the test, reset Rule #5 back to $29/month to avoid polluting other tests.
    """
    import ai_client
    import db
    import ratelimit
    import seed_kb

    ratelimit.reset_rate_limits()
    monkeypatch.setattr(ai_client, "AI_MODE", "rules_only")

    with TestClient(main.app) as client:
        # Reset first so we start from a known clean state
        monkeypatch.setattr(db, "_connect", lambda: None)
        client.post("/api/admin/reset-demo")
        ratelimit.reset_rate_limits()

        # Update chunk 3 via PUT /api/kb/chunks/3
        put_res = client.put(
            "/api/kb/chunks/3",
            json={"chunk_text": "ClaimLoom Pro Plan subscription price is $39/month or $390/year."},
        )
        assert put_res.status_code == 200, put_res.text
        assert put_res.json()["affected_count"] >= 2

        # Scan "$39/month" — should be zero Rule 5 violations
        r39 = client.post("/api/scan-text", json={"text": "The Pro Plan costs $39/month."})
        assert r39.status_code == 200, r39.text
        rule5_violations_39 = [i for i in r39.json()["issues"] if i.get("rule_id") == 5]
        assert len(rule5_violations_39) == 0, f"Expected no Rule 5 violations for $39/month after sync, got: {rule5_violations_39}"

        # Scan "$29/month" — should flag Rule 5 (old price is now wrong)
        r29 = client.post("/api/scan-text", json={"text": "The Pro Plan costs $29/month."})
        assert r29.status_code == 200, r29.text
        rule5_violations_29 = [i for i in r29.json()["issues"] if i.get("rule_id") == 5]
        assert len(rule5_violations_29) > 0, f"Expected Rule 5 violation for $29/month after sync to $39, got none"

        # Reset demo to restore state
        client.post("/api/admin/reset-demo")
