CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS public.brand_rules (
    rule_id INT PRIMARY KEY, workspace_id VARCHAR(64) DEFAULT 'default', version_no INT DEFAULT 1,
    violation_type VARCHAR(50), severity VARCHAR(20), rule_cited TEXT, source_ref TEXT, rule_text TEXT,
    regex_pattern TEXT, default_fix TEXT, claim_status VARCHAR(50), allowed_numbers TEXT,
    applies_to VARCHAR(10) DEFAULT 'text'
);
CREATE TABLE IF NOT EXISTS public.facts (
    fact_id INT PRIMARY KEY, workspace_id VARCHAR(64) DEFAULT 'default', fact_text TEXT, source_ref TEXT
);
CREATE TABLE IF NOT EXISTS public.scans (
    scan_id VARCHAR(50) PRIMARY KEY, readiness_score INT, status VARCHAR(30), created_at TIMESTAMPTZ DEFAULT NOW(),
    input_type VARCHAR(10) DEFAULT 'text', payload JSONB
);
CREATE TABLE IF NOT EXISTS public.flag_events (
    event_id SERIAL PRIMARY KEY, scan_id VARCHAR(50), rule_id INT, action VARCHAR(20), reason TEXT, created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS public.kb_sources (
    source_id SERIAL PRIMARY KEY, workspace_id VARCHAR(64) DEFAULT 'default', doc_title TEXT, source_type VARCHAR(20),
    content_hash VARCHAR(64), version_no INT DEFAULT 1, updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS public.kb_chunks (
    chunk_id SERIAL PRIMARY KEY, source_id INT, workspace_id VARCHAR(64) DEFAULT 'default', doc_title TEXT,
    page_num INT DEFAULT 1, paragraph_num INT DEFAULT 1, chunk_text TEXT, content_hash VARCHAR(64),
    embedding vector(768), updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS public.claim_evidence (
    id SERIAL PRIMARY KEY, scan_id VARCHAR(50), claim_text TEXT, chunk_id INT, verdict VARCHAR(20),
    similarity FLOAT, created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS public.scan_documents (
    scan_id VARCHAR(50) PRIMARY KEY, workspace_id VARCHAR(64) DEFAULT 'default', channel VARCHAR(30) DEFAULT 'general',
    redacted_text TEXT, file_sha256 VARCHAR(64), pdf_bytes BYTEA, result_json JSONB,
    reaudit_needed BOOLEAN DEFAULT FALSE, reaudit_reason TEXT, created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS public.scan_versions (
    version_id SERIAL PRIMARY KEY, scan_id VARCHAR(50), version_no INT, text_snapshot TEXT, score INT,
    actor_name VARCHAR(80), created_at TIMESTAMPTZ DEFAULT NOW(), UNIQUE(scan_id, version_no)
);
CREATE TABLE IF NOT EXISTS public.scan_comments (
    comment_id SERIAL PRIMARY KEY, scan_id VARCHAR(50), author_name VARCHAR(80), author_role VARCHAR(20),
    comment_text TEXT, created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS public.approvals (
    approval_id SERIAL PRIMARY KEY, scan_id VARCHAR(50), version_no INT, text_sha256 VARCHAR(64), score INT,
    reviewer VARCHAR(80), role VARCHAR(20), prev_hash VARCHAR(64), entry_hash VARCHAR(64), signature TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS public.rule_versions (
    id SERIAL PRIMARY KEY, rule_id INT, version_no INT, old_rule_text TEXT, old_pattern TEXT,
    changed_by VARCHAR(80), created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS public.scan_cache (
    cache_key VARCHAR(64) PRIMARY KEY, response_json JSONB, created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS public.kb_meta (
    key TEXT PRIMARY KEY, value INT NOT NULL DEFAULT 1
);

ALTER TABLE public.brand_rules ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(64) DEFAULT 'default';
ALTER TABLE public.brand_rules ADD COLUMN IF NOT EXISTS version_no INT DEFAULT 1;
ALTER TABLE public.brand_rules ADD COLUMN IF NOT EXISTS allowed_numbers TEXT;
ALTER TABLE public.brand_rules ADD COLUMN IF NOT EXISTS applies_to VARCHAR(10) DEFAULT 'text';
ALTER TABLE public.facts ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(64) DEFAULT 'default';
ALTER TABLE public.scans ADD COLUMN IF NOT EXISTS input_type VARCHAR(10) DEFAULT 'text';
ALTER TABLE public.scans ADD COLUMN IF NOT EXISTS payload JSONB;
ALTER TABLE public.scan_documents ADD COLUMN IF NOT EXISTS reaudit_reason TEXT;
ALTER TABLE public.scan_documents ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(64) DEFAULT 'default';
ALTER TABLE public.scan_documents ADD COLUMN IF NOT EXISTS channel VARCHAR(30) DEFAULT 'general';
ALTER TABLE public.scan_documents ADD COLUMN IF NOT EXISTS reaudit_needed BOOLEAN DEFAULT FALSE;
ALTER TABLE public.kb_chunks ADD COLUMN IF NOT EXISTS paragraph_num INT DEFAULT 1;
ALTER TABLE public.kb_chunks ADD COLUMN IF NOT EXISTS doc_title TEXT;
ALTER TABLE public.kb_chunks ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64);
ALTER TABLE public.kb_chunks ADD COLUMN IF NOT EXISTS embedding vector(768);
