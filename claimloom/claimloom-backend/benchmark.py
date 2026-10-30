"""Local TestClient latency benchmark for ClaimLoom Round 3 endpoints."""
from __future__ import annotations

import io
import os
import statistics
import time

try:
    import pymupdf as fitz
except ImportError:
    import fitz
from fastapi.testclient import TestClient

import ai_client
import main

client = TestClient(main.app)
ITERATIONS = 10


def make_pdf() -> bytes:
    doc = fitz.open()
    for page_no in range(2):
        page = doc.new_page()
        page.insert_text((50, 70), f"ClaimLoom brochure page {page_no + 1}: verified battery range is 110 km.")
    result = doc.tobytes()
    doc.close()
    return result


def measure(name, action):
    timings = []
    for iteration in range(ITERATIONS):
        started = time.perf_counter()
        action(iteration)
        timings.append((time.perf_counter() - started) * 1000)
    ordered = sorted(timings)
    p95 = ordered[max(0, min(len(ordered) - 1, int(0.95 * len(ordered) + 0.999) - 1))]
    return {"name": name, "p50": statistics.median(ordered), "p95": p95, "min": ordered[0], "max": ordered[-1]}


def main_benchmark():
    os.environ["AI_MODE"] = "rules_only"
    ai_client.AI_MODE = "rules_only"
    tokens = {}
    for role in ("Creator", "Reviewer"):
        response = client.post("/api/session", json={"name": f"Benchmark {role}", "role": role, "workspace_id": "default"})
        response.raise_for_status()
        tokens[role] = {"Authorization": f"Bearer {response.json()['token']}"}

    metrics = []

    def uncached_text(i):
        response = client.post("/api/scan-text", json={"text": f"Deterministic benchmark run {i}: ClaimLoom supports compliant enterprise teams."}, headers=tokens["Creator"])
        assert response.status_code == 200, response.text
        assert response.json().get("cached") is False

    metrics.append(measure("Uncached deterministic text scan", uncached_text))

    # Exercise the normal successful-AI cache path without making network calls.
    previous_mode, previous_complete = ai_client.AI_MODE, ai_client.complete_json
    ai_client.AI_MODE = "auto"
    ai_client.complete_json = lambda *args, **kwargs: ({"candidates": []}, "benchmark/mock")
    try:
        def cached_text(i):
            text = f"Cache benchmark run {i}: ClaimLoom supports compliant enterprise teams."
            first = client.post("/api/scan-text", json={"text": text}, headers=tokens["Creator"])
            assert first.status_code == 200, first.text
            second = client.post("/api/scan-text", json={"text": text}, headers=tokens["Creator"])
            assert second.status_code == 200 and second.json().get("cached") is True, second.text
        metrics.append(measure("Cached text scan", cached_text))
    finally:
        ai_client.complete_json = previous_complete
        ai_client.AI_MODE = previous_mode

    pdf_bytes = make_pdf()
    pdf_ids = []

    def pdf_scan(i):
        response = client.post("/api/scan-pdf", files={"file": (f"bench-{i}.pdf", pdf_bytes, "application/pdf")}, data={"workspace_id": "default"}, headers=tokens["Creator"])
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["page_count"] == 2
        assert all(isinstance(issue.get("bbox"), list) and len(issue["bbox"]) == 4 for issue in data["issues"])
        pdf_ids.append(data["scan_id"])

    metrics.append(measure("2-page PDF scan + bbox extraction", pdf_scan))

    signed_ids = []

    def redline_export(i):
        response = client.post("/api/scan-text", json={"text": f"Cryptographic certificate benchmark {i}: ClaimLoom helps enterprise teams."}, headers=tokens["Creator"])
        assert response.status_code == 200, response.text
        scan_id = response.json()["scan_id"]
        approval = client.post(f"/api/scans/{scan_id}/approve", json={}, headers=tokens["Reviewer"])
        assert approval.status_code == 200, approval.text
        redline = client.get(f"/api/scans/{scan_id}/redline-pdf")
        assert redline.status_code == 200 and redline.content.startswith(b"%PDF"), redline.text[:200]
        red_doc = fitz.open(stream=redline.content, filetype="pdf")
        try:
            assert "CRYPTOGRAPHIC COMPLIANCE & AUDIT SEAL" in red_doc[-1].get_text()
        finally:
            red_doc.close()
        signed_ids.append(scan_id)

    metrics.append(measure("Redlined PDF export + certificate", redline_export))

    verify_index = 0

    def verify_signature(_i):
        nonlocal verify_index
        scan_id = signed_ids[verify_index]
        verify_index += 1
        response = client.get(f"/api/verify/{scan_id}")
        assert response.status_code == 200 and response.json().get("valid") is True, response.text

    metrics.append(measure("Ed25519 approval signature verification", verify_signature))

    print("| Operation | p50 (ms) | p95 (ms) | Min/Max (ms) |")
    print("|---|---:|---:|---:|")
    for row in metrics:
        print(f"| {row['name']} | {row['p50']:.2f} | {row['p95']:.2f} | {row['min']:.2f} / {row['max']:.2f} |")


if __name__ == "__main__":
    main_benchmark()
