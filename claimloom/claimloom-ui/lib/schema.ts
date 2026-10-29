import { z } from "zod";

export const EvidenceCitationSchema = z
  .object({
    verdict: z.enum(["Verified", "Contradicted", "Unsupported"]).or(z.string()),
    doc_title: z.string(),
    page: z.number().default(1),
    paragraph: z.number().default(1),
    excerpt: z.string(),
    similarity: z.number(),
    chunk_id: z.number().nullable().optional(),
  })
  .passthrough();

export const IssueSchema = z
  .object({
    id: z.string(),
    severity: z.enum(["High", "Medium", "Low"]).or(z.string()),
    violation_type: z
      .enum(["Factual", "Tone", "Terminology", "Accessibility", "Visual"])
      .or(z.string()),
    flagged_text: z.string(),
    start: z.number().nullable().optional().default(null),
    end: z.number().nullable().optional().default(null),
    region: z.any().nullable().optional().default(null),
    rule_id: z.number().nullable().optional().default(null),
    rule_cited: z.string().default("Brand Governance Rule"),
    source_ref: z.string().default("Brand Guidelines"),
    explanation: z.string().default(""),
    suggested_fix: z.string().default(""),
    confidence: z.number().default(0.9),
    detected_by: z.string().default("rule_engine"),
    claim_status: z.string().nullable().optional().default(null),
    // Round 3 v3 fields
    page: z.number().nullable().optional().default(null),
    bbox: z.array(z.number()).nullable().optional().default(null), // [x0, y0, x1, y1] normalized 0..1
    evidence: EvidenceCitationSchema.nullable().optional().default(null),
    channel: z.string().nullable().optional().default("general"),
  })
  .passthrough();

export const ReauditInfoSchema = z
  .object({
    needed: z.boolean().default(false),
    note: z.string().nullable().optional().default(null),
  })
  .passthrough();

export const ScanResponseSchema = z
  .object({
    scan_id: z.string().default("scan_local"),
    input_type: z.string().default("text"), // "text" | "pdf" | "image"
    redacted_text: z.string().nullable().optional().default(null),
    readiness_score: z.number().default(100),
    status: z.string().default("needs_review"),
    ai_status: z.string().default("ok"),
    cached: z.boolean().default(false),
    channel: z.string().default("general"),
    workspace_id: z.string().default("default"),
    kb_version: z.number().default(1),
    rules_version: z.number().default(1),
    page_count: z.number().default(1),
    pillar_scores: z.record(z.string(), z.number()).default({
      tone: 100,
      terminology: 100,
      claims: 100,
      accessibility: 100,
      visual: 100,
    }),
    ai_disclosure: z
      .string()
      .default("Audited by ClaimLoom Two-Tier Engine + Hybrid pgvector/BM25 RAG."),
    pii_redacted_count: z.number().default(0),
    reaudit: ReauditInfoSchema.default({ needed: false, note: null }),
    verified_claims: z.array(EvidenceCitationSchema).default([]),
    issues: z.array(IssueSchema).default([]),
  })
  .passthrough();

export type EvidenceCitation = z.infer<typeof EvidenceCitationSchema>;
export type Issue = z.infer<typeof IssueSchema>;
export type ScanResponse = z.infer<typeof ScanResponseSchema>;