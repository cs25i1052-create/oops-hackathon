"""Run with:  pytest -q      (no real API keys or database needed: the AI is simulated)"""
import io
import json
import os
import sys

import pytest
from fastapi.testclient import TestClient
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import ai_client  # noqa: E402
import db  # noqa: E402
from main import app  # noqa: E402

SAMPLE = "Buy the new claim-loom scooter today! It gives a 200 km range with a 100% guarantee."


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ["GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "CUSTOM_API_KEY", "DATABASE_URL",
              "GROQ_MODELS", "GEMINI_MODELS", "OPENROUTER_MODELS"]:
        monkeypatch.delenv(k, raising=False)
    ai_client.reset_cooldowns()
    monkeypatch.setattr(ai_client, "AI_MODE", "auto")
    monkeypatch.setattr(ai_client, "_successful_provider", None)
    monkeypatch.setattr(ai_client, "_successful_model_by_provider", {})
    db._cache.update(at=0.0, ttl=0)
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def ai_reply(candidates):
    body = {"choices": [{"message": {"content": json.dumps({"candidates": candidates})}}]}
    return 200, json.dumps(body)


# ---------------------------------------------------------------- rule engine
def test_rule_engine_finds_sample_violations_with_exact_positions(client):
    r = client.post("/api/scan-text", json={"text": SAMPLE}).json()
    found = {i["rule_id"]: i for i in r["issues"]}
    assert set(found) == {1, 2, 7}
    for i in r["issues"]:
        assert SAMPLE[i["start"]:i["end"]] == i["flagged_text"]
    assert found[2]["flagged_text"] == "200 km range"
    assert found[2]["claim_status"] == "Outdated Spec"


def test_no_false_positives_on_speed_and_distance(client):
    r = client.post("/api/scan-text", json={"text": "Top speed is 150km/h and the shop is 200 km away."}).json()
    assert r["issues"] == []


def test_catches_variants_old_code_missed(client):
    text = "Our CLAIMLOOM clients love the 115 km range, ZERO RISK, and Pro Plan at $49/month!!"
    ids = {i["rule_id"] for i in client.post("/api/scan-text", json={"text": text}).json()["issues"]}
    assert {1, 2, 3, 5, 7, 14} <= ids


def test_approved_price_is_not_flagged(client):
    r = client.post("/api/scan-text", json={"text": "The Pro Plan costs $29/month."}).json()
    assert r["issues"] == []


def test_singular_and_plural_fix(client):
    issues = client.post("/api/scan-text", json={"text": "Each client and all clients."}).json()["issues"]
    assert [i["suggested_fix"] for i in issues] == ["Creator", "Creators"]


# ---------------------------------------------------------------- positions
def test_emoji_positions_are_utf16(client):
    text = "🚀 Zero risk! Really, zero risk."
    issues = client.post("/api/scan-text", json={"text": text}).json()["issues"]
    assert [(i["start"], i["end"]) for i in issues] == [(3, 12), (22, 31)]  # JS indices, not Python's


def test_leading_whitespace_does_not_shift_highlights(client):
    text = "\n\n   It has zero risk."
    i = client.post("/api/scan-text", json={"text": text}).json()["issues"][0]
    assert text[i["start"]:i["end"]] == "zero risk"


# ---------------------------------------------------------------- AI tier
def test_no_ai_keys_means_degraded_and_never_approved(client):
    r = client.post("/api/scan-text", json={"text": "A perfectly fine sentence."}).json()
    assert r["ai_status"] == "degraded"
    assert r["status"] == "needs_review"  # a gatekeeper must not approve when the AI is down


def test_fallback_to_second_provider_when_first_model_is_retired(client, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("GEMINI_API_KEY", "gem_test")
    calls = []

    def fake_post(url, headers, payload, timeout):
        calls.append((url, payload["model"]))
        if "groq" in url:
            return 404, '{"error":"model not found"}'
        return ai_reply([{"rule_id": 4, "flagged_text": "wipe out every competitor",
                          "explanation": "Aggressive tone.", "suggested_fix": "stand out in the market",
                          "confidence": 0.9, "claim_status": "Outdated Spec"}])

    monkeypatch.setattr(ai_client, "_post", fake_post)
    monkeypatch.setattr(ai_client, "_get", lambda *a, **k: (500, ""))
    text = "We will wipe out every competitor."
    r = client.post("/api/scan-text", json={"text": text}).json()
    assert r["ai_status"] == "ok"
    assert "gemini" in r["ai_disclosure"]
    ai_issue = r["issues"][0]
    assert ai_issue["detected_by"] == "ai" and ai_issue["rule_id"] == 4
    assert text[ai_issue["start"]:ai_issue["end"]] == "wipe out every competitor"
    assert ai_issue["claim_status"] is None  # Tone rule: AI may not set claim_status
    assert any("groq" in c[0] for c in calls)  # it really did try Groq first


def test_dead_models_are_skipped_on_next_request(client, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("GEMINI_API_KEY", "gem_test")
    groq_hits = []

    def fake_post(url, headers, payload, timeout):
        if "groq" in url:
            groq_hits.append(1)
            return 404, "gone"
        return ai_reply([])

    monkeypatch.setattr(ai_client, "_post", fake_post)
    monkeypatch.setattr(ai_client, "_get", lambda *a, **k: (500, ""))
    client.post("/api/scan-text", json={"text": "Hello there."})
    first = len(groq_hits)
    client.post("/api/scan-text", json={"text": "Hello again."})
    assert first > 0 and len(groq_hits) == first  # cooldown: no more wasted calls to the dead models


def test_all_providers_failing_still_returns_rule_results(client, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setattr(ai_client, "_post", lambda *a, **k: (429, "rate limit"))
    monkeypatch.setattr(ai_client, "_get", lambda *a, **k: (500, ""))
    r = client.post("/api/scan-text", json={"text": SAMPLE})
    assert r.status_code == 200
    body = r.json()
    assert body["ai_status"] == "degraded" and len(body["issues"]) == 3


def test_invalid_json_gets_one_repair_retry(client, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    replies = iter([(200, json.dumps({"choices": [{"message": {"content": "Sure! here you go"}}]})),
                    ai_reply([])])
    monkeypatch.setattr(ai_client, "_post", lambda *a, **k: next(replies))
    r = client.post("/api/scan-text", json={"text": "Hello there."}).json()
    assert r["ai_status"] == "ok"


def test_hallucinated_rule_and_invented_text_are_discarded(client, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setattr(ai_client, "_post", lambda *a, **k: ai_reply([
        {"rule_id": 99, "flagged_text": "Hello", "explanation": "x", "suggested_fix": "y"},
        {"rule_id": 4, "flagged_text": "text that is not in the draft", "explanation": "x", "suggested_fix": "y"},
        {"rule_id": 9, "flagged_text": "Hello", "explanation": "image-only rule", "suggested_fix": "y"},
    ]))
    r = client.post("/api/scan-text", json={"text": "Hello there."}).json()
    assert r["issues"] == [] and r["ai_status"] == "ok"


def test_pii_is_masked_before_reaching_the_ai(client, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    seen = []

    def fake_post(url, headers, payload, timeout):
        seen.append(json.dumps(payload))
        return ai_reply([])

    monkeypatch.setattr(ai_client, "_post", fake_post)
    text = "Mail rohit@gmail.com or call +91 98765 43210, card 4111 1111 1111 1111."
    r = client.post("/api/scan-text", json={"text": text}).json()
    assert r["pii_redacted_count"] == 3
    sent = " ".join(seen)
    assert "rohit@gmail.com" not in sent and "98765" not in sent and "4111" not in sent


def test_ai_diagnostic_endpoint(client, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setattr(ai_client, "_post", lambda *a, **k: (404, "gone"))
    prov = client.get("/api/ai-status").json()["providers"]
    groq = next(p for p in prov if p["provider"] == "groq")
    assert groq["configured"] and groq["working_model"] is None and groq["failures"]


# ---------------------------------------------------------------- validation, flag actions
def test_empty_and_oversized_text(client):
    assert client.post("/api/scan-text", json={"text": "   "}).status_code == 400
    assert client.post("/api/scan-text", json={"text": "a" * 8001}).status_code == 422


def test_flag_action_rules(client):
    ok = {"scan_id": "s1", "rule_id": 3, "action": "Accepted"}
    assert client.post("/api/flag-action", json=ok).status_code == 200
    assert client.post("/api/flag-action", json={**ok, "action": "Overridden"}).status_code == 422  # reason required
    assert client.post("/api/flag-action", json={**ok, "rule_id": 999}).status_code == 404


def test_ambiguity_radar_needs_enough_data(client):
    radar = {r["rule_id"]: r for r in client.get("/api/analytics/ambiguity").json()["ambiguity_radar"]}
    assert radar[3]["needs_clarification"] is True      # 2 of 3 overridden
    assert radar[7]["needs_clarification"] is False     # only 1 event: not enough data
    assert radar[7]["enough_data"] is False


def test_scoring_three_issues_lowers_score(client):
    r = client.post("/api/scan-text", json={"text": SAMPLE}).json()
    assert r["readiness_score"] == 100 - (12 + 20 + 20) and r["status"] == "needs_review"


# ---------------------------------------------------------------- images
def png(color_bg, color_fg=None, size=(300, 200), mode="RGB"):
    img = Image.new(mode, size, color_bg)
    if color_fg:
        for x in range(60, 240):
            for y in range(80, 120):
                img.putpixel((x, y), color_fg)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def scan_image(client, data):
    return client.post("/api/scan-image", files={"file": ("a.png", data, "image/png")})


def test_on_brand_high_contrast_image_has_no_color_issues(client):
    r = scan_image(client, png((30, 58, 138), (255, 255, 255))).json()
    assert r["issues"] == []
    assert r["ai_status"] == "degraded"  # no vision key: text in the image was not checked, and it says so


def test_off_brand_color_is_flagged_with_rule_9(client):
    r = scan_image(client, png((200, 30, 30), (255, 255, 255))).json()
    assert 9 in [i["rule_id"] for i in r["issues"]]


def test_low_contrast_graphic_flagged_with_computed_suggestion(client):
    r = scan_image(client, png((255, 255, 255), (240, 240, 240))).json()
    contrast = [i for i in r["issues"] if i["rule_id"] == 10]
    assert contrast and contrast[0]["confidence"] < 1.0
    assert "contrast" in contrast[0]["suggested_fix"]


def test_transparent_png_is_treated_as_white_not_black(client):
    r = scan_image(client, png((0, 0, 0, 0), size=(100, 100), mode="RGBA")).json()
    assert not any("#000000" in i["flagged_text"] for i in r["issues"])


def test_invalid_and_non_image_uploads(client):
    bad = client.post("/api/scan-image", files={"file": ("a.png", b"not an image", "image/png")})
    assert bad.status_code == 400
    txt = client.post("/api/scan-image", files={"file": ("a.txt", b"hello", "text/plain")})
    assert txt.status_code == 400


def test_ocr_text_runs_through_text_pipeline(client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gem_test")

    def fake_post(url, headers, payload, timeout):
        if isinstance(payload["messages"][1]["content"], list):  # the OCR call carries the image
            return 200, json.dumps({"choices": [{"message": {"content": json.dumps({"text": "Zero risk! Buy now"})}}]})
        return ai_reply([])

    monkeypatch.setattr(ai_client, "_post", fake_post)
    r = scan_image(client, png((30, 58, 138), (255, 255, 255))).json()
    assert r["ai_status"] == "ok"
    assert [i["rule_id"] for i in r["issues"]] == [7]
    assert r["issues"][0]["start"] == -1  # no text position in an image
    assert r["issues"][0]["explanation"].startswith("In the image text")


def test_health(client):
    h = client.get("/health").json()
    assert h["status"] == "awake" and h["rules_source"] == "local-fallback"
