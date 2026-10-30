# ClaimLoom — Brand Governance & Approval Ledger

ClaimLoom checks marketing copy and creative assets against brand rules and approved facts, then supports review, remediation, and tamper-evident sign-off. The repository contains a Next.js frontend, FastAPI API v3, PostgreSQL/Neon integration with local seed fallbacks, and a Manifest V3 Chrome extension.

## Live deployments

- **Web app:** [https://oops-hackathon.vercel.app](https://oops-hackathon.vercel.app)
- **API documentation:** [https://oops-hackathon.onrender.com/docs](https://oops-hackathon.onrender.com/docs)

Live availability depends on the hosting service, database, and configured provider keys.

## Three-minute judge evaluation

Use the deployed app and follow the UI labels below. If a scan or seeded record is unavailable, use the nearest newly created scan/rule; demo data can differ by environment.

1. **Text scan:** Open the web app, choose a text sample, and run a scan. Inspect readiness, pillar scores, issue cards, cited rules, and suggested fixes.
2. **Channel rules:** Select **Billboard** (or another channel) and scan copy containing a guarantee, pricing claim, or prohibited phrase. Confirm the channel-specific finding appears alongside the standard rules.
3. **PDF bounding-box redlining + certificate download:** Open the PDF/document flow, upload a small multi-page PDF, inspect highlighted page findings and bounding boxes, then download the redlined PDF. Open its appended certificate page.
4. **Truth Vault price edit + live re-audit:** In **Truth Vault**, locate the pricing source chunk, edit `$29` to `$39`, and save/sync. Review the server’s affected-scan count and re-audit notice; reopen an affected scan if one is returned.
5. **Reviewer Ed25519 sign-off + tamper verification:** Create a disposable clean scan, switch to Reviewer, approve and sign its latest version. Open the certificate and run **Verify Signature**; confirm `valid: true` and `chain_valid: true`. To demonstrate detection on that disposable scan, use the version/editor flow to save one changed text version after signing, then verify again (`GET /api/verify/{scan_id}`); the newer unsigned version should make the response report `tampered: true`. Keep this experiment on a throwaway scan.
6. **Self-healing rule rewrite + backtest + rollback:** In **Governance Radar**, choose a rule, request an AI rewrite, inspect the suggestion, run its backtest, and commit only if appropriate with an Admin role. Use rollback to restore the prior version and verify the returned version number.

The write actions above depend on deployment data and configuration. AI rewrite requires an available AI provider; KB edits require a writable database; elevated session issuance may be disabled in a secured deployment.

## Zero-key local quickstart

The deterministic rules-only backend runs without paid AI keys. From a clone:

```sh
git clone https://github.com/cs25i1052-create/oops-hackathon.git
cd oops-hackathon/claimloom/claimloom-backend
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt pytest
AI_MODE=rules_only uvicorn main:app --reload
```

Then, in another terminal in `claimloom/claimloom-backend`, activate the same environment and run all 26 backend checks:

```sh
AI_MODE=rules_only pytest verify_backend.py -v
```

The suite creates PDFs and images in memory. Install the declared requirements (including PyMuPDF and Pillow) before running it. The under-two-minute goal depends on the machine and dependency-install/cache state; it is not a measured runtime guarantee. On Windows PowerShell, set the mode with `$env:AI_MODE="rules_only"` before `uvicorn` or `pytest`.

For the frontend, use Node 20 in `claimloom/claimloom-ui`, run `npm ci`, then `npm run dev`.

## Repository map

```text
claimloom/
├── claimloom-backend/   FastAPI service, tests, benchmark, extension
├── claimloom-ui/        Next.js application
└── Database/            Database assets

docs/                    Architecture, API, testing, roadmap, changelog
```

## Environment variables

| Variable | Purpose | Required for zero-key local mode? |
|---|---|---|
| `AI_MODE` | `auto` (default) tries configured providers; `rules_only` disables paid AI calls | No; set to `rules_only` for deterministic mode |
| `DATABASE_URL` | PostgreSQL/Neon connection string; absent/unavailable uses supported local read fallbacks | No |
| `SESSION_SECRET` | HMAC session-token signing secret; if absent, process secret is generated (or derived from configured DB URL) | No |
| `SESSION_ISSUER_SECRET` | Restricts elevated role/non-default workspace token issuance when configured | No for local demo; needed by secured deployments |
| `ALLOW_INSECURE_DEMO_ROLES` | Allows demo issuance of elevated roles when no issuer secret is set; default is enabled by code | No |
| `SESSION_TTL_SECONDS` | Session token lifetime; default 7 days | No |
| `GROQ_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `CUSTOM_API_KEY` | Credentials for optional AI providers | No for rules-only |
| `AI_PROVIDER_ORDER` | Provider failover order; defaults to Groq, Gemini, OpenRouter, custom | No |
| `GROQ_MODELS`, `GEMINI_MODELS`, `OPENROUTER_MODELS`, `CUSTOM_MODELS` | Optional comma-separated model overrides | No |
| `CUSTOM_BASE_URL` | OpenAI-compatible custom provider base URL | No |
| `AI_CALL_TIMEOUT`, `AI_TOTAL_TIMEOUT`, `AI_DAILY_LIMIT` | Per-call timeout (12s default), total AI budget (30s), daily call cap (1500) | No |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins; code supplies local and deployed defaults | No |
| `RATE_LIMIT_CAPACITY`, `RATE_LIMIT_REFILL_PER_SEC` | Scan token-bucket settings; code defaults to 30 and 0.1/sec | No |
| `WEBHOOK_SECRET` | Enables authenticated `/api/webhooks/scan` requests | No |
| `SIGNING_PRIVATE_KEY`, `SIGNING_KEY_FALLBACK_SECRET`, `SECRET_KEY` | Optional approval-ledger signing key/fallback configuration | No for ordinary scans; configure deliberately for persistent production signing identity |

Never commit real secrets. See [docs/API.md](docs/API.md) for route contracts and auth details.

## Chrome Extension (Manifest V3)

1. Open `chrome://extensions` and turn on **Developer mode**.
2. Click **Load unpacked** and select `claimloom/claimloom-backend/chrome-extension`.
3. Open the extension popup. It defaults to `https://oops-hackathon.onrender.com`; enable **Use local backend** to switch to `http://localhost:8000`, or edit the backend URL. A custom host prompts Chrome to grant that origin before the scan.
4. Select text on an active tab, or paste text into the popup. Choose a channel and click **Scan copy**.
5. Review readiness score, pillar scores, and issue cards. Use **Copy Suggested Fix** on a card to copy its fix.

The extension sends scans to `POST /api/scan-text`. Local use requires the backend to be running and reachable from Chrome.

## Engineering docs

- [Architecture](docs/ARCHITECTURE.md)
- [API v3](docs/API.md)
- [Testing and benchmark](docs/TESTING.md)
- [Roadmap](docs/ROADMAP.md)
- [Changelog](docs/CHANGELOG.md)


