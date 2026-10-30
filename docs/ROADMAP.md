# Roadmap

## Shipped in Round 3

- Deterministic text governance with channel-specific rules, scoring, PII redaction, and optional multi-provider AI fallback.
- PDF and supported document scans, PDF layout/bounding-box findings, image analysis, and redlined PDF export.
- Truth Vault chunks and evidence linking, rule versioning/backtests/rollback, scan comments and versions, re-audit signaling, and Ed25519 hash-chained approvals with verification.
- Next.js UI, API v3 routes, Chrome extension, backend verification suite, and local benchmark harness.

These statements describe code present in this repository; individual capabilities may use local fallback data when Neon is unavailable. Provider-backed AI rewrite/vision features need suitable keys.

## Phase 4 — planned, not shipped

- Native `.pptx` parsing and slide-level review.
- Figma desktop plugin using the shared REST API.
- Live Notion OAuth and connected-workspace synchronization.
- OCR coverage beyond the current planned three scanned pages (scope and implementation still to be delivered).
- Video and audio content auditing.

Phase 4 items are roadmap commitments only; this repository does not currently ship them as complete integrations.
