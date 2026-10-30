# ClaimLoom — Intelligent Pre-Publication Brand Governance & Claim Verification Platform

**CodeAxis Hackathon (Round 3 Final Submission) • Problem Statement: InkLoom AI**  
**Team:** Coders | **Institution:** IIITDM Kancheepuram

[![Live Web App](https://img.shields.io/badge/Live_Web_App-oops--hackathon.vercel.app-1E3A8A?style=for-the-badge&logo=vercel)](https://oops-hackathon.vercel.app)
[![Backend API Docs](https://img.shields.io/badge/FastAPI_Swagger_Docs-onrender.com%2Fdocs-059669?style=for-the-badge&logo=fastapi)](https://oops-hackathon.onrender.com/docs)
[![Engine Health](https://img.shields.io/badge/Health_Check-%2Fhealth-FF5500?style=for-the-badge)](https://oops-hackathon.onrender.com/health)
[![Chrome Extension ZIP](https://img.shields.io/badge/Chrome_Extension-Download_.zip-0F172A?style=for-the-badge&logo=googlechrome)](https://oops-hackathon.onrender.com/api/extension/download)

---

## 1. Executive Overview

Modern marketing, design, and legal teams publish promotional copy, multi-page brochures, and visual banners across distributed channels and generative AI tools—frequently leaking unverified product specs, outdated pricing, off-brand hex colors, and accessibility violations.

**ClaimLoom** is a zero-login, full-stack pre-publication governance gatekeeper that audits **marketing copy**, **multi-page PDF brochures**, **Word/Markdown documents**, and **visual graphics** against grounded company facts and brand rules before publication. Instead of acting as a black-box blocker, ClaimLoom:

1. **Pinpoints exact character spans or spatial bounding boxes** ($[x_0, y_0, x_1, y_1]$) across text, PDFs, and images.
2. **Verifies quantitative claims** against an authoritative **Truth Vault** using a Hybrid RAG pipeline (`pgvector` $768$-dim cosine similarity + `BM25Okapi` lexical scoring fused via Reciprocal Rank Fusion).
3. **Provides 1-click context-preserving fixes** (including singular/plural grammatical inflection matching) and word-level visual diffs.
4. **Enforces a Multi-Role Cryptographic Sign-Off Gate** backed by hash-chained **Ed25519** signatures, downloadable **Redlined PDFs**, and a **Self-Healing Governance Radar**.

---

## 2. Live Deployment Links (100% Open & Zero-Login)

| Component | Live URL | Notes |
| :--- | :--- | :--- |
| **Web Application (Next.js 16 on Vercel)** | **[https://oops-hackathon.vercel.app](https://oops-hackathon.vercel.app)** | Zero-login workspace with instant presets, role switcher, and offline fallback. |
| **Backend API & Swagger UI (FastAPI on Render)** | **[https://oops-hackathon.onrender.com/docs](https://oops-hackathon.onrender.com/docs)** | Interactive OpenAPI specification for all $27$ REST endpoints. |
| **Keep-Alive Ping ($< 5\text{ ms}$)** | **[https://oops-hackathon.onrender.com/ping](https://oops-hackathon.onrender.com/ping)** | Lightweight zero-DB liveness probe monitored by `cron-job.org`. |
| **Database & Vault Diagnostics** | **[https://oops-hackathon.onrender.com/health](https://oops-hackathon.onrender.com/health)** | Reports active rules source (`neon_pg` / `local_seed`) and connection status. |
| **Chrome Extension Bundle (`.zip`)** | **[https://oops-hackathon.onrender.com/api/extension/download](https://oops-hackathon.onrender.com/api/extension/download)** | 1-click Manifest V3 Chrome Extension package. |
| **GitHub Repository** | **[https://github.com/cs25i1052-create/oops-hackathon](https://github.com/cs25i1052-create/oops-hackathon)** | Full monorepo (`claimloom-backend`, `claimloom-ui`, `Database`). |

---

## 3. Judge Quickstart: 2-Minute End-to-End Walkthrough (No Setup Required)

Open **[https://oops-hackathon.vercel.app](https://oops-hackathon.vercel.app)** and test the four core workflows directly in your browser:

1. **Studio Tab (Two-Tier Text Audit, Auto-Fix & Ed25519 Sign-Off):**
   - Click **Try a sample: `With violations`** and click **Run audit**.
   - Inspect inline severity highlights, verified Truth Vault citations, and the 5-pillar Readiness Score.
   - Click **Apply all fixes** (or switch to the **Changes** tab to inspect the word-level diff), then click **Approve and sign** as **Reviewer** to generate a tamper-evident **Ed25519 Cryptographic Certificate** verified via `/api/verify/{scan_id}`.
2. **Canvas Tab (Multi-Page PDF Spatial Bounding Boxes & Redlined PDF Export):**
   - Switch to the **Canvas** tab and click **Load sample brochure** (or upload any `.pdf`, `.png`, `.jpg`, `.docx`, or `.md` file up to $5\text{ MB}$).
   - Click any red/amber bounding box on the rendered page preview to jump to its sidebar finding (including sub-$9\text{pt}$ micro-print and WCAG contrast flags).
   - Click **Download redlined PDF** to export the annotated brochure with a signed **Compliance Certificate** appended as the final page.
3. **Truth Vault Tab (Live Price Change $\$29 \rightarrow \$39$ & Re-Audit Cascade):**
   - Open the **Truth Vault** tab and click **Demo Price Change ($\$29$ to $\$39$) & Sync**.
   - Watch ClaimLoom re-index Chunk #3 in Neon, dynamically update Brand Rule #5 to enforce $\$39/\text{month}$, and flag dependent historical scans as `needs_reaudit`.
   - Click **Reset** in the header at any time to restore the baseline $\$29/\text{month}$ state.
4. **Governance Radar & Chrome Extension Simulator:**
   - Open **Governance Radar** to inspect workspace telemetry and high-override rules (e.g., Rule #3). Click **Propose AI Rule Rewrite** $\rightarrow$ **Backtest & Commit** (protected by our AST-level ReDoS safety guard) $\rightarrow$ **Rollback**.
   - Click **🧩 Chrome Extension** in the top navbar to download the Manifest V3 `.zip` bundle or test the **Live Popup Simulator** directly inside the modal.

---

## 4. Complete Feature List & Round 3 Improvements Delivered

### Core Engine & Multimodal Auditing
* **Two-Tier Hybrid Engine (`POST /api/scan-text`):** Combines $< 10\text{ ms}$ Tier-1 deterministic regex rules with Tier-2 multi-provider LLM semantic analysis (Groq `llama-3.3-70b-versatile` / `llama-3.1-8b-instant` and Google Gemini `gemini-2.5-flash` / `gemini-2.0-flash`) with $60\text{-second}$ circuit-breaker failover.
* **16 Core Brand Rules + 10 Channel Playbook Rules:** Specialized rules for **General Marketing**, **LinkedIn** (max $5$ hashtags, no DM-bait, no all-caps words), **Instagram** (no raw URLs, $150$-word paragraph cap), **Highway Billboard** ($12$-word OOH legibility cap, no web URLs), and **Email** (spam phrase & consecutive all-caps guards).
* **Same-Length Pre-AI PII Redaction:** Scrubs email addresses, phone numbers, and $16$-digit payment cards with exact-length `'X'` masks before external LLM calls so character offsets remain $1:1$ with user input.
* **Unicode & Astral-Plane UTF-16 Offset Mapping (`to_utf16`):** Converts Python code-point indices into JavaScript UTF-16 code units so inline highlights never drift on emojis (`🚀`, `🔥`) or RTL Arabic script.
* **Multimodal Image Auditor (`POST /api/scan-image`):** Computes CIE76 $L^*a^*b^*$ $\Delta E$ color distance against the official brand palette (`#1E3A8A`, `#FF5500`, `#FFFFFF`, `#0F172A` with threshold $\Delta E \le 25.0$), WCAG 2.1 AA contrast ratios ($\ge 4.5:1$), RGBA white alpha-compositing, and automatic 1-page PDF conversion for Canvas rendering.
* **Word & Markdown Document Ingestion (`POST /api/scan-doc`):** Extracts paragraphs and table cells from `.docx`, `.md`, `.markdown`, and `.txt` files.

### Round 3 Committed Improvements
* **Improvement 1 — Multi-Page PDF Spatial Layout Engine & Redlining (`pdf_engine.py`, `CanvasTab.tsx`):**
  * Extracts page-level text and normalized $[x_0, y_0, x_1, y_1]$ bounding boxes via PyMuPDF (`fitz`) with multi-line whitespace/quote-normalized fallback search.
  * Audits sub-$9\text{pt}$ micro-print legibility (Rule 10), pages exceeding $3$ font families (Rule 9), and WCAG 2.1 AA ($4.5:1$) text-to-background pixel contrast via $0.5\times$ pixmap sampling.
  * Renders server-side page PNGs (`GET /api/scans/{id}/page/{n}.png`) and generates downloadable **Redlined PDFs** (`GET /api/scans/{id}/redline-pdf`) with red callout boxes and an appended **Ed25519 Compliance Certificate** page.
* **Improvement 2 — Hybrid RAG Fact Verifier & Automated Truth Vault Sync (`rag_verifier.py`, `kb_router.py`, `VaultTab.tsx`):**
  * Combines $768$-dim Gemini vector embeddings in Neon `pgvector` with `rank_bm25.BM25Okapi` lexical scoring via Reciprocal Rank Fusion ($\text{RRF} = \frac{1}{60 + \text{rank}}$) and a $\ge 0.72$ similarity threshold.
  * Extracts numerical claims and units (`km`, `%`, `$`, `minutes`, `years`) while filtering out unrelated speed/distance contexts (`150km/h`, `200 km away`).
  * Attaches verbatim `EvidenceCitation` badges (`doc_title`, `page`, `paragraph`, `excerpt`, `similarity`) and cascades `needs_reaudit` flags across `claim_evidence` whenever Truth Vault facts change.
* **Improvement 3 — Collaborative Governance, Ed25519 Signing, Chrome Extension & Self-Healing Rules (`collab_router.py`, `signing.py`, `rules_router.py`, `chrome-extension/`):**
  * Zero-login stateless HMAC-SHA256 role switcher (**Creator**, **Reviewer**, **Admin**) and workspace isolation (**ClaimLoom Official** vs. **My Custom Brand Sandbox**).
  * High-severity blocker gate (`HTTP 409 Conflict`), 3-second polling review threads, and hash-chained **Ed25519** signatures with public tamper verification at `GET /api/verify/{scan_id}`.
  * Self-Healing Governance Radar with AI rule rewrites (`POST /api/rules/{id}/rewrite`), `sre_parse` AST ReDoS validation + $100$-scan backtesting (`POST /api/rules/{id}/backtest`), and 1-click version rollback (`POST /api/rules/{id}/rollback`).
  * Manifest V3 Chrome Extension + authenticated CMS webhook (`POST /api/webhooks/scan`).

---

## 5. System Architecture & Repository Structure

```text
┌───────────────────────────────────────────────────────────────────────────────────┐
│                   FRONTEND WORKSPACE (Vercel • Next.js 16 + React 19)             │
│   Studio Editor (UTF-16 Highlights & Word Diffs) │ Interactive PDF/Image Canvas   │
│   Truth Vault (Live Price Sync & Rule Builder)   │ Governance Radar & Ext Modal   │
└─────────────────────────────────────────┬─────────────────────────────────────────┘
                                          │ HTTPS REST + Stateless HMAC-SHA256
                                          ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│                   BACKEND ENGINE (Render • Python FastAPI)                        │
│  ┌────────────────────┐  ┌──────────────────────┐  ┌───────────────────────────┐  │
│  │ 1. Ingress Shield  │  │ 2. Tier-1 & Spatial  │  │ 3. Hybrid RAG Verifier    │  │
│  │ • XFF Rate Limiter │─▶│ • 16 Brand + 10 Chan │─▶│ • pgvector (768-dim)      │  │
│  │ • Same-Length PII  │  │ • PyMuPDF BBox/Font  │  │ • BM25Okapi + RRF Fusion  │  │
│  │ • SHA-256 Cache    │  │ • CIE76 ΔE + WCAG    │  │ • Unit/Number Cross-Check │  │
│  └────────────────────┘  └──────────────────────┘  └─────────────┬─────────────┘  │
│                                                                  ▼                │
│  ┌────────────────────────────────────┐  ┌─────────────────────────────────────┐  │
│  │ 5. Governance & Ed25519 Signing    │◀─│ 4. Tier-2 AI Failover & Guard       │  │
│  │ • Hash-Chained Ed25519 Approvals   │  │ • Groq (Llama 3.3 70B / 3.1 8B)     │  │
│  │ • Redlined PDF + Certificate Gen   │  │ • Gemini (2.5 Flash / 2.0 Flash)    │  │
│  │ • ReDoS AST Guard & Rule Backtest  │  │ • Hallucination & No-Op Span Filter │  │
│  └────────────────────────────────────┘  └─────────────────────────────────────┘  │
└─────────────────────────────────────────┬─────────────────────────────────────────┘
                                          │ Sticky Serialized Connection + LRU Cache
                                          ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│              CLOUD DATABASE (Neon Serverless PostgreSQL + pgvector)               │
│  brand_rules │ rule_history │ facts │ kb_chunks (HNSW vector(768)) │ approvals    │
│  scan_documents (SHA-256 deduplicated PDFs) │ scan_versions │ claim_evidence      │
└───────────────────────────────────────────────────────────────────────────────────┘
```

### Monorepo Directory Layout

```text
oops-hackathon/
├── claimloom-backend/               # FastAPI Backend & Audit Engine
│   ├── main.py                      # App lifecycle, /ping, /health, /api/scan-text, /api/extension/download
│   ├── pipeline.py                  # 5-stage audit orchestration, overlap deduplication & scoring
│   ├── engine.py                    # Tier-1 regex engine, 10 channel playbooks, PII redaction, UTF-16 mapper
│   ├── ai_client.py                 # Multi-provider Groq -> Gemini failover & hallucination filter
│   ├── rag_verifier.py              # Hybrid pgvector + BM25Okapi RRF verifier & unit/number extractor
│   ├── pdf_engine.py                # PyMuPDF spatial bbox extractor, font/contrast checks & PDF redliner
│   ├── vision_router.py             # Pillow CIE76 ΔE color math, WCAG contrast, Vision OCR & PDF bridge
│   ├── kb_router.py                 # Truth Vault CRUD, live price sync ($29->$39) & re-audit cascade
│   ├── collab_router.py             # Versions, review thread comments, 409 gate & Ed25519 sign-off
│   ├── rules_router.py              # Ambiguity radar, AI rule rewriter, ReDoS AST guard & backtester
│   ├── signing.py                   # Ed25519 keypair management & SHA-256 hash-chain verification
│   ├── session.py                   # Stateless HMAC-SHA256 role & workspace token verification
│   ├── ratelimit.py                 # Proxy-aware X-Forwarded-For token bucket rate limiter
│   ├── cache.py                     # 128-entry SHA-256 scan LRU cache (skips degraded AI states)
│   ├── db.py                        # Thread-safe Neon PostgreSQL connection wrapper & local seed fallback
│   ├── migrations/001_round3.sql    # Full PostgreSQL + pgvector schema migration
│   ├── chrome-extension/            # Manifest V3 Chrome Extension (manifest.json, popup.html/js/css)
│   ├── tests/                       # Automated pytest suites (test_backend.py, test_round3.py)
│   └── verify_backend.py            # 26-assertion standalone backend verification runner
├── claimloom-ui/                    # Next.js 16 + React 19 + TypeScript + Tailwind v4 Frontend
│   ├── app/                         # App Router layout, global styles & main workspace page
│   ├── components/                  # EditorCard, ResultsPanel, CanvasTab, VaultTab, RadarTab, Modals
│   └── lib/                         # API client, workspace hook, offline engine fallback & schemas
└── Database/                        # Standalone Neon pgvector & Gemini embedding setup scripts
```

---

## 6. Local Installation & Setup Guide (Clone & Run in $< 5\text{ Minutes}$)

ClaimLoom is engineered with **graceful zero-dependency fallbacks**: you can clone and run the entire backend and frontend locally **even without a PostgreSQL database or external LLM API keys** (it automatically falls back to deterministic rules and seeded in-memory Truth Vault data), or connect it to Neon PostgreSQL + Groq/Gemini for full cloud functionality.

### Prerequisites
* **Python:** $3.10+$
* **Node.js:** $18.18+$ or $20+$ (`npm`)
* **Git**

### Step 1: Clone the Repository

```bash
git clone https://github.com/cs25i1052-create/oops-hackathon.git
cd oops-hackathon
```

### Step 2: Set Up & Start the FastAPI Backend (`claimloom-backend`)

```bash
cd claimloom-backend
python3 -m venv .venv
source .venv/bin/activate   # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

*(Optional)* Create a `.env` file in `claimloom-backend/.env` if you want live LLM inference and Neon PostgreSQL persistence (if omitted, the server runs cleanly using `seed_db.py` and `seed_kb.py`):

```env
# Optional — falls back to deterministic rules + local seed data if omitted
DATABASE_URL=postgresql://user:password@ep-example.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
GROQ_API_KEY=gsk_your_groq_key_here
GEMINI_API_KEY=your_gemini_key_here

# Session & Signing Secrets (auto-generated in dev if omitted)
CLAIMLOOM_SESSION_SECRET=local-dev-hmac-secret-key
CLAIMLOOM_SIGNING_SEED=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
WEBHOOK_SECRET=claimloom-webhook-secret
AI_MODE=auto
```

*(Optional)* If using a fresh Neon PostgreSQL database, apply the schema migration and seed data:

```bash
psql "$DATABASE_URL" -f migrations/001_round3.sql
python3 seed_db.py
python3 seed_kb.py
```

Start the FastAPI server on `http://localhost:8000`:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Step 3: Set Up & Start the Next.js Frontend (`claimloom-ui`)

Open a second terminal window:

```bash
cd claimloom-ui
npm install
```

Create `claimloom-ui/.env.local` pointing to your local backend:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Start the Next.js development server on `http://localhost:3000`:

```bash
npm run dev
```

Open **[http://localhost:3000](http://localhost:3000)** in your browser.

### Step 4: Load the Chrome Extension (Unpacked)

1. Open Google Chrome and navigate to `chrome://extensions`.
2. Enable **Developer mode** (toggle in the top-right corner).
3. Click **Load unpacked** and select the `claimloom-backend/chrome-extension/` directory (or download the `.zip` directly from the web UI header button).

---

## 7. Running the Automated Verification & Testing Suites

From `claimloom-backend/` (with your virtual environment activated), run our automated test suites:

```bash
cd claimloom-backend

# 1. Run the 26-check standalone backend verification suite:
python3 verify_backend.py

# 2. Run all unit & Round 3 integration tests via pytest:
pytest -q

# 3. Run the 42-case master audit & asset generator (if master_audit_and_ping.py is saved):
python3 master_audit_and_ping.py
```

Verify the frontend production build from `claimloom-ui/`:

```bash
cd claimloom-ui
npm run build
```

---

## 8. Key API Endpoints Reference

| Method & Path | Description | Auth / Role |
| :--- | :--- | :--- |
| `GET /ping` | Sub-$5\text{ ms}$ zero-DB keep-alive probe for uptime monitors. | Public |
| `GET /health` | Database connectivity and active rules/facts source diagnostic. | Public |
| `POST /api/session` | Issues a stateless HMAC-SHA256 token for `Creator`, `Reviewer`, or `Admin`. | Public |
| `POST /api/scan-text` | Runs the Two-Tier + Hybrid RAG audit on marketing copy ($1\text{–}8,000$ chars). | Any Role |
| `POST /api/scan-pdf` | Audits multi-page PDFs (text, sub-$9\text{pt}$ fonts, $>3$ fonts, WCAG contrast, bboxes). | Any Role |
| `POST /api/scan-sample-pdf` | Generates and audits a 2-page sample brochure PDF for 1-click demos. | Any Role |
| `POST /api/scan-image` | Audits PNG/JPG/WebP banners (CIE76 $\Delta E$, WCAG contrast, Vision OCR, PDF bridge). | Any Role |
| `POST /api/scan-doc` | Extracts and audits `.docx` (paragraphs + tables), `.md`, and `.txt` documents. | Any Role |
| `GET /api/scans/{id}/page/{n}.png` | Renders page $n$ of a scanned PDF or image as a PNG for the Canvas overlay. | Public |
| `GET /api/scans/{id}/redline-pdf` | Exports a Redlined PDF with red callout boxes + signed Ed25519 Certificate page. | Public |
| `POST /api/scans/{id}/versions` | Saves a new edited draft version snapshot and recalculates readiness score. | Any Role |
| `POST /api/scans/{id}/comments` | Posts a role-badged reviewer note to the scan's collaborative thread. | Any Role |
| `POST /api/scans/{id}/approve` | Enforces the HTTP 409 blocker gate and signs the scan with Ed25519. | `Reviewer` / `Admin` |
| `GET /api/verify/{id}` | Publicly verifies the Ed25519 signature and hash chain (`tampered` detection). | Public |
| `GET /api/kb/sources` | Lists indexed Truth Vault documents, chunks, and active `kb_version`. | Any Role |
| `PUT /api/kb/chunks/{id}` | Updates a Truth Vault fact, syncs Rule #5 pricing, and flags dependent scans. | Any Role |
| `POST /api/rules/{id}/rewrite` | Uses AI to propose a clearer rule definition and ReDoS-safe regex pattern. | `Reviewer` / `Admin` |
| `POST /api/rules/{id}/backtest` | Validates regex AST against ReDoS and backtests against $100$ historical scans. | `Reviewer` / `Admin` |
| `POST /api/rules/{id}/rollback` | Rolls back a brand rule to its previous version from `rule_history`. | `Admin` |
| `GET /api/extension/download` | Streams `ClaimLoom-Chrome-Extension.zip` for 1-click browser installation. | Public |
| `POST /api/webhooks/scan` | Headless CMS / CI-CD pre-publish webhook (`X-Webhook-Secret`). | Webhook Secret |

---

## 9. Product Roadmap

* **Phase 1 (Weeks 1–4) — Native Figma & Adobe Express Plugins + Vector Logo Geometry:** Export Figma frames directly to `/api/scan-image`, map $[x_0, y_0, x_1, y_1]$ bounding boxes back onto canvas layers, and add OpenCV template matching for $0.25\times$ logo clear-space geometry on $2\text{ GB}$ RAM worker nodes.
* **Phase 2 (Months 2–3) — Asynchronous Batch Auditing & Google Docs / Notion / HubSpot Sync:** Introduce an Upstash Redis + ARQ task queue (`POST /api/scan-batch`) for $500$-asset campaign ZIPs and push Truth Vault re-audit alerts directly as inline comments inside Google Docs and HubSpot drafts.
* **Phase 3 (Months 4–6) — Multi-Jurisdiction Regulatory Packs & Hardware KMS Signing:** Deliver toggleable legal packs (ASCI EV greenwashing, SEBI/RBI financial disclaimers, FTC endorsement guides), SAML 2.0 SSO (WorkOS), Neon Row-Level Security (RLS), and AWS KMS hardware-backed Ed25519 keys.
* **Phase 4 (Months 6–12) — Video & Audio Storyboard Compliance Auditing:** Combine FFmpeg keyframe extraction and Whisper audio transcription with ClaimLoom's Hybrid RAG and CIE76 visual engine to audit YouTube/Reels video ads.

---

## 10. Team Coders — Contributors & Architecture Ownership

| Team Member | Role & Core Module Ownership | Institutional Email | GitHub |
| :--- | :--- | :--- | :--- |
| **Rohit Bansode** | **Team Lead & UI / Frontend Architect**<br>Next.js 16 workspace, character-span highlight & word-diff editor, Interactive PDF Canvas, Truth Vault & Governance Radar UI, Chrome Extension Simulator modal, Vercel CI/CD | `cs25i1008@iiitdm.ac.in` | [@br768](https://github.com/br768) |
| **Pratik Kiran Bainade** | **Backend & Hybrid AI Pipeline Engineer**<br>FastAPI routers (`main.py`, `pdf_engine.py`, `vision_router.py`, `collab_router.py`, `rules_router.py`, `kb_router.py`, `webhook_router.py`), PyMuPDF redlining, Ed25519 signing, ReDoS guard, rate limiter, Render deploy | `cs25i1052@iiitdm.ac.in` | [@cs25i1052-create](https://github.com/cs25i1052-create) |
| **Devraj Tangade** | **Database & Vector Infrastructure Architect**<br>Neon Serverless PostgreSQL schema & Round 3 migrations (`001_round3.sql`), sticky connection pool (`db.py`), `pgvector` $768$-dim embeddings, Hybrid BM25 + `pgvector` RRF verifier (`rag_verifier.py`), audit telemetry | `cs25b1067@iiitdm.ac.in` | [@Devraj-Tangade](https://github.com/cs25i1052-create/oops-hackathon) |