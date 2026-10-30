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
  "inline-flex items-center justify-center gap-1.5 rounded-full bg-blue-600 px-4 py-2 text-xs font-semibold text-white shadow-xs transition-all hover:bg-blue-700 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600/40 focus-visible:ring-offset-2";
export const btnDark =
  "inline-flex items-center justify-center rounded-full bg-slate-900 px-3.5 py-1.5 text-xs font-semibold text-white transition-all hover:bg-slate-800 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-700/40";
export const btnGhost =
  "inline-flex items-center justify-center rounded-full border border-slate-200/80 bg-white/90 px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs transition-all hover:bg-slate-100 hover:text-slate-900 active:scale-95 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400/40";
export const inputCls =
  "w-full rounded-xl border border-slate-200/80 bg-white/90 px-3.5 py-2 text-xs text-slate-900 placeholder:text-slate-400 shadow-2xs focus:border-blue-500 focus:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/20 transition-all";
export const selectCls =
  "rounded-full border border-slate-200/80 bg-white/90 px-3 py-1.5 text-xs font-semibold text-slate-800 shadow-2xs focus:border-blue-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/20 transition-all";

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
