"use client";

import React, { useMemo, useState } from "react";
import type { Issue } from "../lib/schema";
import { Card } from "./Common";
import { btnGhost, btnPrimary, resolveRange, selectCls } from "../lib/ui";

export const MAX_CHARS = 8000;

export const CHANNELS = [
  { id: "general", label: "General marketing copy" },
  { id: "linkedin", label: "LinkedIn B2B post" },
  { id: "instagram", label: "Instagram caption" },
  { id: "billboard", label: "Billboard (12 words max)" },
  { id: "email", label: "Customer email" },
];

type View = "edit" | "findings" | "changes";
const VIEWS: { id: View; label: string }[] = [
  { id: "edit", label: "Edit" },
  { id: "findings", label: "Findings" },
  { id: "changes", label: "Changes" },
];

type Segment = { text: string; id?: string; severity?: string };

function buildSegments(text: string, issues: Issue[]): Segment[] {
  const lower = text.toLowerCase();
  const ranges: { start: number; end: number; id: string; severity: string }[] = [];

  for (const issue of issues) {
    const exact = resolveRange(text, issue);
    if (exact) {
      ranges.push({ ...exact, id: issue.id, severity: issue.severity });
      continue;
    }
    const needle = issue.flagged_text?.toLowerCase();
    if (!needle) continue;
    let from = 0;
    for (;;) {
      const at = lower.indexOf(needle, from);
      if (at === -1) break;
      ranges.push({ start: at, end: at + needle.length, id: issue.id, severity: issue.severity });
      from = at + needle.length;
    }
  }
  ranges.sort((a, b) => a.start - b.start);

  const segments: Segment[] = [];
  let cursor = 0;
  for (const r of ranges) {
    if (r.start < cursor) continue; 
    if (r.start > cursor) segments.push({ text: text.slice(cursor, r.start) });
    segments.push({ text: text.slice(r.start, r.end), id: r.id, severity: r.severity });
    cursor = r.end;
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor) });
  return segments;
}

interface Props {
  text: string;
  onTextChange: (value: string) => void;
  original: string;
  channel: string;
  onChannelChange: (value: string) => void;
  isScanning: boolean;
  scanStep: string;
  onRun: () => void;
  onUploadClick: () => void;
  onSample: (kind: "violation" | "clean" | "brochure") => void;
  issues: Issue[];
  selectedIssueId: string | null;
  onSelectIssue: (id: string) => void;
}

export default function EditorCard({
  text,
  onTextChange,
  original,
  channel,
  onChannelChange,
  isScanning,
  scanStep,
  onRun,
  onUploadClick,
  onSample,
  issues,
  selectedIssueId,
  onSelectIssue,
}: Props) {
  const [view, setView] = useState<View>("edit");
  const segments = useMemo(
    () => (view === "findings" ? buildSegments(text, issues) : []),
    [view, text, issues]
  );
  const trimmedLength = text.trim().length;
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  const overLimit = trimmedLength > MAX_CHARS;

  return (
    <Card className="p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Copy editor</h2>
          <p className="text-xs text-slate-500">
            Paste marketing copy, or{" "}
            <button
              type="button"
              onClick={onUploadClick}
              disabled={isScanning}
              className="font-medium text-blue-700 hover:underline disabled:opacity-50"
            >
              upload a PDF or image
            </button>{" "}
            (5 MB max).
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="sr-only" htmlFor="channel">
            Target channel
          </label>
          <select id="channel" value={channel} onChange={(e) => onChannelChange(e.target.value)} className={selectCls}>
            {CHANNELS.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
          <div role="group" aria-label="Editor view" className="inline-flex overflow-hidden rounded-lg border border-slate-300">
            {VIEWS.map((v) => (
              <button
                key={v.id}
                type="button"
                aria-pressed={view === v.id}
                onClick={() => setView(v.id)}
                className={`px-3 py-1.5 text-xs font-semibold transition ${
                  view === v.id ? "bg-slate-900 text-white" : "bg-white text-slate-700 hover:bg-slate-50"
                }`}
              >
                {v.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {view === "edit" && (
        <textarea
          aria-label="Marketing copy"
          value={text}
          onChange={(e) => onTextChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              onRun();
            }
          }}
          rows={8}
          placeholder="Paste promotional copy, product specs or press release text here."
          className="w-full resize-y rounded-lg border border-slate-300 bg-slate-50 p-4 text-sm leading-relaxed text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:bg-white focus:outline-2 focus:outline-blue-500/30"
        />
      )}

      {view === "findings" && (
        <div>
          <div className="min-h-[12rem] whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm leading-relaxed text-slate-900">
            {!text.trim() ? (
              <span className="text-slate-400">Nothing to show yet.</span>
            ) : (
              segments.map((s, i) =>
                s.id ? (
                  <button
                    key={i}
                    type="button"
                    onClick={() => onSelectIssue(s.id as string)}
                    className={`rounded px-0.5 font-medium underline decoration-2 underline-offset-2 ${
                      s.severity === "High"
                        ? "bg-red-100 text-red-900 decoration-red-500"
                        : "bg-amber-100 text-amber-900 decoration-amber-500"
                    } ${s.id === selectedIssueId ? "ring-2 ring-blue-500" : ""}`}
                  >
                    {s.text}
                  </button>
                ) : (
                  <span key={i}>{s.text}</span>
                )
              )
            )}
          </div>
          <p className="mt-2 text-xs text-slate-500">
            {issues.length === 0
              ? "No findings to highlight. Run an audit first."
              : "Click a highlight to select its finding."}
          </p>
        </div>
      )}

      {view === "changes" && (
        <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm leading-relaxed">
          <div>
            <p className="mb-1 text-xs font-semibold text-slate-500">Original</p>
            <p className="whitespace-pre-wrap text-slate-500 line-through decoration-red-400">
              {original || "No baseline yet. Run an audit first."}
            </p>
          </div>
          <div>
            <p className="mb-1 text-xs font-semibold text-emerald-700">Current</p>
            <p className="whitespace-pre-wrap font-medium text-slate-900">{text || "Nothing written yet."}</p>
          </div>
        </div>
      )}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <span className={`text-xs ${overLimit ? "font-semibold text-red-600" : "text-slate-500"}`}>
          {trimmedLength.toLocaleString()} / {MAX_CHARS.toLocaleString()} characters, {words} words
        </span>
        <button type="button" onClick={onRun} disabled={isScanning} className={btnPrimary}>
          {isScanning ? scanStep || "Auditing..." : "Run audit"}
        </button>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4 text-xs text-slate-500">
        Try a sample:
        <button type="button" onClick={() => onSample("violation")} className={btnGhost}>
          With violations
        </button>
        <button type="button" onClick={() => onSample("clean")} className={btnGhost}>
          Compliant
        </button>
        <button type="button" onClick={() => onSample("brochure")} className={btnGhost}>
          Brochure on canvas
        </button>
      </div>
    </Card>
  );
}