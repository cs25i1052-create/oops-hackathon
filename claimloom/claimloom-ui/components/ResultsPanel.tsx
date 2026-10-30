"use client";

import React, { memo, useEffect, useRef, useState } from "react";
import type { Issue, ScanResponse } from "../lib/schema";
import { Card, Empty } from "./Common";
import { btnDark, btnGhost, Origin, prettyStatus, scoreTone, sevStyle } from "../lib/ui";
import { logFlagAction } from "../lib/api";

const PILLARS: Record<string, string> = {
  tone: "Tone",
  terminology: "Terminology",
  claims: "Claims",
  accessibility: "Accessibility",
  visual: "Visual",
};

const Chip = ({ children, cls = "bg-slate-100 text-slate-600" }: { children: React.ReactNode; cls?: string }) => (
  <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${cls}`}>{children}</span>
);

interface CardProps {
  issue: Issue;
  selected: boolean;
  scanId: string;
  onSelect: (id: string) => void;
  onLocate: (issue: Issue) => void;
  onAccept: (issue: Issue) => void;
  onOverride: (issue: Issue, reason: string) => void;
}

const IssueCard = memo(function IssueCard({ issue, selected, scanId, onSelect, onLocate, onAccept, onOverride }: CardProps) {
  const ref = useRef<HTMLElement>(null);
  const [showOverride, setShowOverride] = useState(false);
  const [overrideReason, setOverrideReason] = useState("");

  useEffect(() => {
    if (selected) ref.current?.scrollIntoView({ block: "nearest" });
  }, [selected]);
  const s = sevStyle(issue.severity);

  const handleConfirmOverride = () => {
    void logFlagAction(scanId, issue.rule_id || 3, "Overridden", overrideReason);
    onOverride(issue, overrideReason);
    setShowOverride(false);
    setOverrideReason("");
  };

  return (
    <article
      ref={ref}
      onClick={() => onSelect(issue.id)}
      className={`space-y-3 rounded-xl border border-l-4 bg-white p-4 shadow-sm ${s.edge} ${
        selected ? "border-blue-300 ring-2 ring-blue-500/30" : "border-slate-200"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className={`rounded px-2 py-0.5 text-xs font-semibold ${s.pill}`}>
          {issue.severity}, {issue.violation_type}
        </span>
        {issue.bbox && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onLocate(issue);
            }}
            className="text-xs font-semibold text-blue-700 hover:underline"
          >
            Show on canvas
          </button>
        )}
      </div>
      <h3 className="text-sm font-semibold leading-snug">{issue.rule_cited}</h3>
      <dl className="space-y-1.5 rounded-lg bg-slate-50 p-3 text-xs">
        <div className="flex gap-2">
          <dt className="w-12 shrink-0 font-semibold text-red-700">Found</dt>
          <dd className="text-slate-800">{issue.flagged_text}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="w-12 shrink-0 font-semibold text-emerald-700">Fix</dt>
          <dd className="text-slate-800">{issue.suggested_fix}</dd>
        </div>
      </dl>
      <details className="text-xs text-slate-600" onClick={(e) => e.stopPropagation()}>
        <summary className="cursor-pointer font-semibold text-blue-700">Why this was flagged</summary>
        <div className="mt-2 space-y-2">
          <p>{issue.explanation}</p>
          <p className="text-slate-500">
            Rule source: {issue.source_ref}. Found by {issue.detected_by.replace(/_/g, " ")} with{" "}
            {Math.round((issue.confidence ?? 1) * 100)}% confidence.
          </p>
          {issue.evidence && (
            <p className="border-t border-slate-200 pt-2 text-slate-500">
              Evidence: {issue.evidence.doc_title}, p.{issue.evidence.page} (
              {Math.round(issue.evidence.similarity * 100)}% match). &ldquo;{issue.evidence.excerpt}&rdquo;
            </p>
          )}
        </div>
      </details>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onAccept(issue);
          }}
          className={`${btnDark} flex-1`}
        >
          Accept fix
        </button>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setShowOverride((v) => !v);
          }}
          className={`${btnGhost} flex-shrink-0`}
        >
          Override
        </button>
      </div>
      {showOverride && (
        <div className="space-y-2" onClick={(e) => e.stopPropagation()}>
          <input
            type="text"
            value={overrideReason}
            onChange={(e) => setOverrideReason(e.target.value)}
            placeholder="Reason for override (e.g., B2B legal quote)"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          <button
            type="button"
            onClick={handleConfirmOverride}
            className={`${btnDark} w-full`}
          >
            Confirm override
          </button>
        </div>
      )}
    </article>
  );
});

interface Props {
  scanResult: ScanResponse | null;
  isScanning: boolean;
  origin: Origin;
  selectedIssueId: string | null;
  onSelect: (id: string) => void;
  onLocate: (issue: Issue) => void;
  onAccept: (issue: Issue) => void;
  onOverride: (issue: Issue, reason: string) => void;
  onSample: (kind: "violation" | "clean" | "brochure") => void;
}

function ResultsPanel({ scanResult, isScanning, origin, selectedIssueId, onSelect, onLocate, onAccept, onOverride, onSample }: Props) {
  if (isScanning) {
    return (
      <div className="space-y-4" aria-busy="true" aria-label="Audit in progress">
        <div className="h-44 animate-pulse rounded-xl border border-slate-200 bg-white" />
        {[1, 2].map((n) => (
          <div key={n} className="animate-pulse space-y-3 rounded-xl border border-slate-200 bg-white p-5">
            <div className="h-4 w-1/3 rounded bg-slate-200" />
            <div className="h-4 w-full rounded bg-slate-200" />
            <div className="h-12 w-full rounded bg-slate-100" />
          </div>
        ))}
      </div>
    );
  }

  if (!scanResult) {
    return (
      <Empty
        title="No audit yet"
        body="Run an audit on your copy, upload a document, or load a sample to see the score and findings here."
      >
        <button type="button" onClick={() => onSample("violation")} className={btnGhost}>
          Load a sample
        </button>
      </Empty>
    );
  }

  const issues = scanResult.issues;
  const highCount = issues.filter((i) => i.severity === "High").length;
  const tone = scoreTone(scanResult.readiness_score);

  return (
    <div className="space-y-4">
      <Card className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-medium text-slate-500">Readiness score</p>
            <p className={`text-4xl font-bold tabular-nums ${tone.text}`}>
              {scanResult.readiness_score}
              <span className="text-base font-normal text-slate-400"> / 100</span>
            </p>
          </div>
          <Chip cls={issues.length === 0 ? "bg-emerald-50 text-emerald-800" : tone.pill}>
            {issues.length === 0
              ? "Compliant"
              : `${issues.length} ${issues.length === 1 ? "issue" : "issues"}, ${highCount} high`}
          </Chip>
        </div>

        <div className="mt-3 flex flex-wrap gap-1.5">
          <Chip>Status: {prettyStatus(scanResult.status)}</Chip>
          {origin === "sample" && <Chip>Sample data</Chip>}
          {origin === "fallback" && <Chip cls="bg-amber-50 text-amber-800">Offline demo result</Chip>}
          {scanResult.cached && <Chip cls="bg-blue-50 text-blue-800">Cached result</Chip>}
          {scanResult.ai_status !== "ok" && (
            <Chip cls="bg-amber-50 text-amber-800">AI layer: {prettyStatus(scanResult.ai_status)}</Chip>
          )}
        </div>

        <div className="mt-4 space-y-2">
          {Object.entries(scanResult.pillar_scores).map(([key, value]) => (
            <div key={key} className="flex items-center gap-3 text-xs">
              <span className="w-24 shrink-0 text-slate-600">{PILLARS[key] ?? key}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                <div className={`h-full rounded-full ${scoreTone(value).bar}`} style={{ width: `${value}%` }} />
              </div>
              <span className="w-8 text-right tabular-nums text-slate-500">{value}</span>
            </div>
          ))}
        </div>

        {scanResult.pii_redacted_count > 0 && (
          <p className="mt-3 rounded-lg bg-slate-50 p-2.5 text-xs text-slate-600">
            {scanResult.pii_redacted_count} personal data {scanResult.pii_redacted_count === 1 ? "item was" : "items were"}{" "}
            redacted before analysis.
          </p>
        )}

        {scanResult.verified_claims.length > 0 && (
          <details className="mt-4 border-t border-slate-100 pt-3">
            <summary className="cursor-pointer text-xs font-semibold text-emerald-700">
              {scanResult.verified_claims.length} verified {scanResult.verified_claims.length === 1 ? "claim" : "claims"}{" "}
              (grounded in your Truth Vault)
            </summary>
            <div className="mt-2 space-y-2">
              {scanResult.verified_claims.map((vc, idx) => (
                <div key={idx} className="rounded-lg bg-emerald-50 p-2.5 text-xs text-emerald-900">
                  <div className="font-semibold">
                    {vc.doc_title}, p.{vc.page} ({Math.round(vc.similarity * 100)}% match)
                  </div>
                  <div className="mt-0.5 italic text-emerald-800">&ldquo;{vc.excerpt}&rdquo;</div>
                </div>
              ))}
            </div>
          </details>
        )}

        <p className="mt-4 border-t border-slate-100 pt-3 text-[11px] leading-snug text-slate-400">
          {scanResult.ai_disclosure}
        </p>
      </Card>

      {issues.length === 0 ? (
        <Card className="border-emerald-200 p-5 text-center">
          <p className="text-sm font-semibold text-emerald-800">No compliance issues remaining.</p>
        </Card>
      ) : (
        <div className="max-h-[560px] space-y-3 overflow-y-auto pr-1">
          {issues.map((issue) => (
            <IssueCard
              key={issue.id}
              issue={issue}
              selected={selectedIssueId === issue.id}
              scanId={scanResult.scan_id}
              onSelect={onSelect}
              onLocate={onLocate}
              onAccept={onAccept}
              onOverride={onOverride}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default memo(ResultsPanel);
