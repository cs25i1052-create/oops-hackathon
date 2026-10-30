# API v3

Base URL is the FastAPI service (local default `http://localhost:8000`). JSON endpoints return JSON unless identified as a file/image. The main scan response includes `scan_id`, `readiness_score`, `status`, `ai_status`, `pillar_scores`, `issues`, `input_type`, `cached`, `channel`, `workspace_id`, `rules_version`, `kb_version`, `page_count`, `verified_claims`, and `reaudit`. Each issue includes severity/type, flagged text and offsets, rule citation, explanation, suggested fix, detector, and optional page/bounding box/evidence.

Role tokens are issued by `POST /api/session` and sent as `Authorization: Bearer <token>`. Missing auth falls back to unauthenticated Creator for legacy/basic scan routes. “Reviewer/Admin” means either role. Elevated session issuance can be disabled or require `X-Session-Issuer-Secret` depending on deployment configuration. Workspace access is checked against the token on supported routes.

| Method & path | Request | Response / behavior | Role |
|---|---|---|---|
| `GET /ping` | — | Awake status; DB-free | Public |
| `GET /health` | — | DB/rules and configured AI status | Public |
| `GET /api/ai-status` | — | Provider status and AI budget | Public |
| `POST /api/session` | `{role?, name?, workspace_id?}` | `{token, role, name, workspace_id, expires_at}` | Public; elevated issuance may require secret |
| `GET /api/session/me` | Bearer optional | Current `SessionUser` | Any session / Creator fallback |
| `POST /api/scan-text` | `{text (max 8000), channel?, workspace_id?}` | Scan response | Creator+ |
| `POST /api/scan-pdf` | multipart `file`, optional form `channel`, `workspace_id` | Scan response; max 5 MB and 10 pages | Creator+ |
| `POST /api/scan-doc` | multipart `file` (DOCX/Markdown/text supported by implementation), optional form fields | Scan response | Creator+ |
| `POST /api/scan-image` | multipart `file`, optional form fields | Scan response; image limit 8 MB | Creator+ |
| `GET /api/scans/{scan_id}` | — | Stored scan response | Public in current router |
| `GET /api/scans/{scan_id}/page/{n}.png` | — | Rendered PNG page | Public in current router |
| `GET /api/scans/{scan_id}/redline-pdf` | — | Redlined PDF with certificate page | Public in current router |
| `POST /api/scans/{scan_id}/versions` | `{text_snapshot}` | Creates version and scan result | Current router does not require a role |
| `POST /api/scans/{scan_id}/comments` | `{comment_text}` | Created comment | Current router does not require a role |
| `GET /api/scans/{scan_id}/activity` | — | Comments/activity and re-audit state | Current router does not require a role |
| `POST /api/scans/{scan_id}/approve` | `{version_no?}` | `{status, approval, public_key}` | Reviewer/Admin |
| `GET /api/verify/{scan_id}` | — | Signature, content and hash-chain validity | Public verification |
| `GET /api/public-key` | — | Ed25519 public key | Public |
| `GET /api/rules` | optional `workspace_id`, `refresh` | Rules, facts, source/version data | Public |
| `POST /api/rules` | `violation_type`, `rule_cited`, `rule_text`; optional severity/source/regex/fix/applies_to/workspace_id | Created rule and version | Admin |
| `PATCH /api/rules/{rule_id}` | Rule fields to update | Updated rule/version | Admin |
| `POST /api/rules/{rule_id}/rewrite` | — | Proposed rule text/regex, rationale, model | Reviewer/Admin; AI may be unavailable |
| `POST /api/rules/{rule_id}/backtest` | `{proposed_regex?}` | Evaluated scans, old/new flags and safety results | Reviewer/Admin |
| `POST /api/rules/{rule_id}/rollback` | `{version_no?}` | Restored version | Admin |
| `GET /api/analytics/summary` | — | Scan, score, approvals, re-audit and version summary | Public |
| `GET /api/analytics/ambiguity` | — | Rule override/ambiguity radar | Public |
| `POST /api/flag-action` | `{scan_id, rule_id, action, reason?}`; override requires reason | Recorded action | Current route accepts session; no explicit role gate |
| `GET /api/kb/sources` | optional `workspace_id` | KB sources/chunks and version | Public |
| `PUT /api/kb/chunks/{chunk_id}` | `{chunk_text, doc_title?}` | Updated chunk and affected scans | Current router does not require a role |
| `PUT /api/facts/{chunk_id}` | `{chunk_text, doc_title?}` | Compatibility alias for chunk update | Current router does not require a role |
| `POST /api/kb/sync` | — | KB version and affected scans | Current router does not require a role |
| `POST /api/admin/reset-demo` | — | Reset status and versions | Current router does not require a role; protect deployment access |
| `POST /api/webhooks/scan` | `{text, channel?, workspace_id?}` + `X-Webhook-Secret` | Scan response | Shared webhook secret |

## Common status codes

| Code | Meaning in this API |
|---|---|
| `400` | Empty text, malformed input/file, 10-page PDF cap, unsupported or invalid operation |
| `401` | Missing/invalid webhook secret or malformed/expired bearer token where supplied |
| `403` | Role, issuer-secret, or workspace authorization denied |
| `409` | Approval blocked by re-audit, blockers, or non-latest version |
| `413` | Multipart upload size limit exceeded (5 MB PDF/document, 8 MB image) |
| `422` | Request schema/field/regex validation failure; oversized JSON text is rejected by the 8,000-character field constraint |
| `429` | Scan token-bucket rate limit reached (`Retry-After` included) |
| `503` | Required provider/database feature unavailable (for example AI rewrite, KB write, or session issuance) |

Not every endpoint emits every code in the table. FastAPI validation and route-specific failures also use `404`, `500`, and `502` where applicable. This table describes observed behavior, not a promise that all errors are normalized identically.

