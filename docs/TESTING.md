# Testing and benchmarks

Run from `claimloom/claimloom-backend` after installing `requirements.txt` and `pytest`:

```sh
AI_MODE=rules_only pytest verify_backend.py -v
python3 benchmark.py
```

PowerShell equivalent for the first command: `$env:AI_MODE="rules_only"; pytest verify_backend.py -v`. The test module uses FastAPI `TestClient`, PyMuPDF, Pillow, and in-memory PDF/image fixtures. `rules_only` avoids external paid model calls; several checks still exercise app-level degraded-mode reporting. Database-backed features use local fallback behavior where implemented, but DB write checks require a configured database or the test's mocked/local paths.

## 26-check coverage matrix

| Checks | Coverage |
|---|---|
| 1–3 | DB-free ping, health diagnostics, issue and verify Creator/Reviewer/Admin sessions |
| 4–5 | Billboard/channel rule scan, ClaimLoom no-op false-positive guard, scan reload |
| 6–8 | Two-page PDF scan, normalized bounding boxes, layout/contrast checks, PNG preview, redline and certificate page |
| 9–10 | Markdown/DOCX document ingestion; image CIE76 visual check and bounding box |
| 11–13 | Reviewer comments, approval blocker gate, versioning, Ed25519 signature and hash-chain tamper detection |
| 14–16 | Regex safety/backtest, rule patch and rollback, ambiguity/analytics telemetry |
| 17 | Proxy-aware token-bucket rate limiting |
| 18–20 | Empty/whitespace and oversized text rejection; emoji/RTL UTF-16 highlight offsets |
| 21–23 | Invalid, encrypted and over-10-page PDF rejection |
| 24–25 | Creator role denied on Admin rule operations; broad regex rejected without corrupting rules |
| 26 | `AI_MODE=rules_only` reports degraded AI and does not mark clean scan approved |

## Latency benchmark

`benchmark.py` runs 10 iterations for deterministic uncached text scans, cached text scans, 2-page PDF scan plus bounding-box extraction, redlined PDF/certificate export, and Ed25519 verification. It prints p50, p95, and min/max in Markdown. These measurements are machine- and environment-dependent and should be generated on the target machine before being quoted.

**Current checked-in measurement: not available.** The benchmark has not been successfully run in this checkout, so no p50/p95 numbers are claimed here. Run `python3 benchmark.py` and paste its output below when dependencies and runtime are available. Do not substitute estimates.
