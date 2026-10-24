import { z } from "zod";

export const IssueSchema = z.object({
  id: z.string().default(() => crypto.randomUUID()),
  severity: z.enum(["High", "Medium", "Low"]).catch("High"),
  violation_type: z.enum(["Tone", "Factual", "Visual"]).catch("Tone"),
  flagged_text: z.string(),
  start: z.number().nullish().transform((v) => v ?? -1),
  end: z.number().nullish().transform((v) => v ?? -1),
  rule_cited: z.string(),
  explanation: z.string().optional(),
  suggested_fix: z.string(),
  confidence: z.number().nullish().transform((v) => v ?? undefined),
});

export const ScanResponseSchema = z.object({
  scan_id: z.string().optional(),
  readiness_score: z.number().optional(),
  status: z.string().optional(),
  pillar_scores: z.record(z.string(), z.number()).optional(),
  ai_disclosure: z.string().optional(),
  issues: z.array(IssueSchema),
});

export type Issue = z.infer<typeof IssueSchema>;
export type ScanResponse = z.infer<typeof ScanResponseSchema>;