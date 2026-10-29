import type { Issue } from "./schema";

export type Tab = "studio" | "canvas" | "vault" | "radar";
export type Role = "Creator" | "Reviewer" | "Admin";
export type Origin = "live" | "sample" | "fallback";

export interface BrandRule {
  id: number;
  name: string;
  category: string;
  severity: string;
  pattern: string;
}

export const btnPrimary =
  "inline-flex items-center justify-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600";
export const btnDark =
  "inline-flex items-center justify-center rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:bg-slate-300 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-slate-900";
export const btnGhost =
  "inline-flex items-center justify-center rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600";
export const inputCls =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-blue-500 focus:outline-2 focus:outline-blue-500/30";
export const selectCls =
  "rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs font-medium text-slate-800 focus:border-blue-500 focus:outline-2 focus:outline-blue-500/30";

export function errMsg(e: unknown): string {
  if (e instanceof Error) {
    if (e.name === "AbortError") return "The request timed out";
    if (e.name === "ZodError") return "The server response did not match the expected format";
    return e.message.length > 160 ? `${e.message.slice(0, 160)}...` : e.message;
  }
  return "Unknown error";
}

export function calcScore(issues: Issue[]): number {
  const high = issues.filter((i) => i.severity === "High").length;
  const other = issues.length - high;
  return Math.max(0, Math.min(100, 100 - high * 25 - other * 10));
}

export function scoreTone(score: number) {
  if (score >= 85) return { text: "text-emerald-700", bar: "bg-emerald-500", pill: "bg-emerald-50 text-emerald-800" };
  if (score >= 60) return { text: "text-amber-700", bar: "bg-amber-500", pill: "bg-amber-50 text-amber-800" };
  return { text: "text-red-700", bar: "bg-red-500", pill: "bg-red-50 text-red-800" };
}

export function sevStyle(severity: string) {
  return severity === "High"
    ? { dot: "bg-red-500", pill: "bg-red-50 text-red-700", edge: "border-l-red-500", box: "border-red-500 bg-red-500/15" }
    : { dot: "bg-amber-500", pill: "bg-amber-50 text-amber-800", edge: "border-l-amber-500", box: "border-amber-500 bg-amber-400/15" };
}

export const prettyStatus = (s: string) => s.replace(/_/g, " ");

export function resolveRange(text: string, issue: Issue): { start: number; end: number } | null {
  const { start, end, flagged_text } = issue;
  if (start == null || end == null || !flagged_text) return null;
  if (start < 0 || end > text.length || start >= end) return null;
  if (text.slice(start, end).toLowerCase() !== flagged_text.toLowerCase()) return null;
  return { start, end };
}
