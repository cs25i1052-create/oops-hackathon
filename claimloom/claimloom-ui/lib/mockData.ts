import { ScanResponse } from "./schema";

export const SAMPLE_VIOLATION_TEXT =
  "Get our ClaimLoom software for guaranteed 100% results! The Pro Plan costs $15/month and gives 110 km certified range.";

export const SAMPLE_CLEAN_TEXT =
  "Discover how ClaimLoom helps marketing teams streamline compliance checks. The Pro Plan costs $29/month and delivers a certified 110 km range under standard testing conditions.";

export const MOCK_SCAN_RESPONSE_V3: ScanResponse = {
  scan_id: "scan_r3demo01",
  input_type: "pdf",
  redacted_text: SAMPLE_VIOLATION_TEXT,
  readiness_score: 48,
  status: "needs_review",
  ai_status: "ok",
  cached: false,
  channel: "general",
  workspace_id: "default",
  kb_version: 1,
  rules_version: 1,
  page_count: 2,
  pillar_scores: {
    tone: 65,
    terminology: 100,
    claims: 40,
    accessibility: 90,
    visual: 85,
  },
  ai_disclosure:
    "Audited by ClaimLoom Two-Tier Engine (Deterministic Regex/CIE76 + Groq LLM & Hybrid pgvector/BM25 RAG).",
  pii_redacted_count: 0,
  reaudit: { needed: false, note: null },
  verified_claims: [
    {
      verdict: "Verified",
      doc_title: "Product_Spec_Sheet_2026.md",
      page: 1,
      paragraph: 2,
      excerpt:
        "Maximum certified battery range is 110 km per charge under standard testing conditions.",
      similarity: 0.93,
      chunk_id: 1,
    },
  ],
  issues: [
    {
      id: "iss_1",
      severity: "High",
      violation_type: "Factual",
      flagged_text: "$15/month",
      start: 75,
      end: 84,
      region: null,
      rule_id: 5,
      rule_cited: "Brand Rule 5: Pro Plan Pricing Accuracy",
      source_ref: "Approved_Pricing_Policy.md, p.1",
      explanation:
        "Contradicts verified pricing fact ($29/month billed monthly or $290/year).",
      suggested_fix: "$29/month",
      confidence: 0.96,
      detected_by: "rag_verifier",
      claim_status: "Contradicted Fact",
      page: 1,
      bbox: [0.12, 0.42, 0.52, 0.50],
      evidence: {
        verdict: "Contradicted",
        doc_title: "Approved_Pricing_Policy.md",
        page: 1,
        paragraph: 1,
        excerpt:
          "The ClaimLoom Pro Plan subscription costs $29/month billed monthly, or $290/year.",
        similarity: 0.91,
        chunk_id: 3,
      },
      channel: "general",
    },
    {
      id: "iss_2",
      severity: "High",
      violation_type: "Tone",
      flagged_text: "guaranteed 100% results!",
      start: 31,
      end: 55,
      region: null,
      rule_id: 3,
      rule_cited: "Brand Rule 3: No Unsubstantiated Superlatives or Guarantees",
      source_ref: "Legal_Warranty_Terms.md, p.2",
      explanation:
        "Absolute performance guarantees ('guaranteed 100% results') violate FTC truth-in-advertising guidelines.",
      suggested_fix: "measurable compliance improvements.",
      confidence: 0.98,
      detected_by: "rule_engine",
      claim_status: "Unsupported Claim",
      page: 1,
      bbox: [0.12, 0.22, 0.78, 0.31],
      evidence: {
        verdict: "Unsupported",
        doc_title: "Legal_Warranty_Terms.md",
        page: 2,
        paragraph: 4,
        excerpt:
          "Marketing materials must never promise 100% guaranteed outcomes without regulatory certification.",
        similarity: 0.88,
        chunk_id: 4,
      },
      channel: "general",
    },
    {
      id: "iss_3",
      severity: "Medium",
      violation_type: "Accessibility",
      flagged_text: "Footer Disclaimer (7.5pt font, Contrast 2.8:1)",
      start: null,
      end: null,
      region: null,
      rule_id: 14,
      rule_cited: "Brand Rule 14: WCAG 2.1 AA Minimum Contrast & Typography",
      source_ref: "Visual_Accessibility_Standard.md, p.1",
      explanation:
        "PDF footer text uses 7.5pt font (minimum is 9pt) and has a contrast ratio of 2.8:1 against the background (WCAG AA requires 4.5:1).",
      suggested_fix: "Increase font size to 10pt and use #1E3A8A or #0F172A text.",
      confidence: 1.0,
      detected_by: "pdf_layout",
      claim_status: null,
      page: 1,
      bbox: [0.12, 0.78, 0.88, 0.86],
      evidence: null,
      channel: "general",
    },
  ],
};

export const MOCK_CLEAN_SCAN_V3: ScanResponse = {
  ...MOCK_SCAN_RESPONSE_V3,
  scan_id: "scan_r3clean02",
  input_type: "text",
  redacted_text: SAMPLE_CLEAN_TEXT,
  readiness_score: 98,
  status: "needs_review",
  pillar_scores: {
    tone: 100,
    terminology: 100,
    claims: 100,
    accessibility: 95,
    visual: 100,
  },
  verified_claims: [
    {
      verdict: "Verified",
      doc_title: "Approved_Pricing_Policy.md",
      page: 1,
      paragraph: 1,
      excerpt: "The ClaimLoom Pro Plan subscription costs $29/month billed monthly.",
      similarity: 0.95,
      chunk_id: 3,
    },
    {
      verdict: "Verified",
      doc_title: "Product_Spec_Sheet_2026.md",
      page: 1,
      paragraph: 2,
      excerpt: "Maximum certified battery range is 110 km per charge.",
      similarity: 0.93,
      chunk_id: 1,
    },
  ],
  issues: [],
};

export interface KBChunkItem {
  chunk_id: number;
  doc_title: string;
  page: number;
  category: string;
  fact_text: string;
  updated_at: string;
}

export const INITIAL_KB_CHUNKS: KBChunkItem[] = [
  {
    chunk_id: 1,
    doc_title: "Product_Spec_Sheet_2026.md",
    page: 1,
    category: "Product Specs",
    fact_text: "Maximum certified battery range is 110 km per charge under standard testing conditions.",
    updated_at: "2026-10-28 09:00",
  },
  {
    chunk_id: 2,
    doc_title: "Product_Spec_Sheet_2026.md",
    page: 2,
    category: "Charging",
    fact_text: "Fast-charge technology restores battery from 0% to 80% in 45 minutes.",
    updated_at: "2026-10-28 09:00",
  },
  {
    chunk_id: 3,
    doc_title: "Approved_Pricing_Policy.md",
    page: 1,
    category: "Pricing",
    fact_text: "The ClaimLoom Pro Plan subscription costs $29/month billed monthly, or $290/year.",
    updated_at: "2026-10-28 09:00",
  },
  {
    chunk_id: 4,
    doc_title: "Legal_Warranty_Terms.md",
    page: 2,
    category: "Legal & SLA",
    fact_text: "Enterprise tier includes a 99.9% uptime SLA and a 2-year limited hardware warranty.",
    updated_at: "2026-10-28 09:00",
  },
  {
    chunk_id: 5,
    doc_title: "Visual_Accessibility_Standard.md",
    page: 1,
    category: "Visual & Accessibility",
    fact_text: "Approved brand palette is #1E3A8A (Navy), #FF5722 (Accent), and #FFFFFF. Body text requires 4.5:1 WCAG AA contrast and >= 9pt size.",
    updated_at: "2026-10-28 09:00",
  },
];