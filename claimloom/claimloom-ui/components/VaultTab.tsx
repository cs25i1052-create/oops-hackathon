"use client";

import React, { memo, useCallback, useEffect, useRef, useState } from "react";
import type { KBChunkItem } from "../lib/mockData";
import { Card } from "./Common";
import { BrandRule, btnPrimary, inputCls } from "../lib/ui";
import { API_BASE, ensureSessionToken, getAuthHeaders } from "../lib/api";

interface Props {
  workspaceId: string;
  kbVersion: number;
  chunks: KBChunkItem[];
  affectedCount: number;
  onSync: () => void;
  rules: BrandRule[];
  onDataLoaded?: (rules: BrandRule[], chunks: KBChunkItem[], rulesVersion: number, kbVersion: number) => void;
  onAffected?: (count: number, ids: string[], version: number) => void;
}

interface BackendRule { rule_id: number; rule_cited: string; violation_type: string; severity: string; rule_text: string; }
interface BackendChunk { chunk_id: number; doc_title: string; page_num: number; chunk_text: string; updated_at?: string | null; }
interface RulesResponse { rules?: BackendRule[]; rules_version?: number; }
interface SourcesResponse { chunks?: BackendChunk[]; kb_version?: number; }

function VaultTab({ workspaceId, kbVersion, chunks, affectedCount, onSync, rules, onDataLoaded, onAffected }: Props) {
  const [name, setName] = useState("");
  const [pattern, setPattern] = useState("");
  const [alert, setAlert] = useState("");
  const [busy, setBusy] = useState(false);
  const ready = name.trim().length > 0 && pattern.trim().length > 0;

  const dataLoadedRef = useRef(onDataLoaded);
  const affectedRef = useRef(onAffected);
  useEffect(() => { dataLoadedRef.current = onDataLoaded; }, [onDataLoaded]);
  useEffect(() => { affectedRef.current = onAffected; }, [onAffected]);

  const refresh = useCallback(async () => {
    try {
      const [ruleRes, kbRes] = await Promise.all([
        fetch(`${API_BASE}/api/rules?refresh=true&workspace_id=${encodeURIComponent(workspaceId)}`, { headers: getAuthHeaders() }),
        fetch(`${API_BASE}/api/kb/sources?workspace_id=${encodeURIComponent(workspaceId)}`, { headers: getAuthHeaders() }),
      ]);
      const ruleData = ruleRes.ok ? ((await ruleRes.json()) as RulesResponse) : {};
      const kbData = kbRes.ok ? ((await kbRes.json()) as SourcesResponse) : {};

      const mappedRules: BrandRule[] = (ruleData.rules || []).map((r) => ({
        id: r.rule_id,
        name: r.rule_cited,
        category: r.violation_type,
        severity: r.severity,
        pattern: r.rule_text,
      }));
      const mappedChunks: KBChunkItem[] = (kbData.chunks || []).map((c) => ({
        chunk_id: c.chunk_id,
        doc_title: c.doc_title,
        page: c.page_num,
        category: "Knowledge Base",
        fact_text: c.chunk_text,
        updated_at: c.updated_at || "",
      }));

      if (mappedRules.length > 0 || mappedChunks.length > 0) {
        dataLoadedRef.current?.(mappedRules, mappedChunks, ruleData.rules_version || 1, kbData.kb_version || 1);
        setAlert("");
      } else if (!ruleRes.ok && !kbRes.ok) {
        throw new Error("Could not connect to live Truth Vault backend.");
      }
    } catch (e) {
      setAlert(e instanceof Error ? e.message : "Refresh failed");
    }
  }, [workspaceId]);
  useEffect(() => { const timer = window.setTimeout(() => void refresh(), 0); return () => window.clearTimeout(timer); }, [refresh]);

  const submit = () => {
    if (!ready) return;
    void (async () => {
      setBusy(true); setAlert("");
      try {
        await ensureSessionToken("Admin", localStorage.getItem("cl_name") || "Judge Reviewer", workspaceId);
        const response = await fetch(`${API_BASE}/api/rules`, { method: "POST", headers: getAuthHeaders({ "Content-Type": "application/json" }), body: JSON.stringify({ violation_type: "Tone", severity: "Medium", rule_cited: name.trim(), source_ref: "Custom Workspace Guideline", rule_text: pattern.trim(), regex_pattern: null, default_fix: null, applies_to: "text", workspace_id: workspaceId }) });
        const data = await response.json().catch((): { detail?: string } => ({}));
        if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data));
        setName(""); setPattern(""); await refresh();
      } catch (e) { setAlert(e instanceof Error ? e.message : "Could not add rule"); }
      finally { setBusy(false); }
    })();
  };

  const updateChunk = async (chunk: KBChunkItem, text: string) => {
    try {
      const response = await fetch(`${API_BASE}/api/kb/chunks/${chunk.chunk_id}`, { method: "PUT", headers: getAuthHeaders({ "Content-Type": "application/json" }), body: JSON.stringify({ chunk_text: text }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Chunk update failed");
      affectedRef.current?.(data.affected_count || 0, data.affected_scans || [], data.kb_version || kbVersion);
      await refresh();
    } catch (e) { setAlert(e instanceof Error ? e.message : "Chunk update failed"); }
  };

  const resetDemo = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/admin/reset-demo`, { method: "POST", headers: getAuthHeaders() });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.detail || "Reset failed");
      }
      setAlert("");
      await refresh();
    } catch (e) { setAlert(e instanceof Error ? e.message : "Reset failed"); }
  };

  return (
    <div className="space-y-6">
      <Card className="flex flex-wrap items-center justify-between gap-4 p-5 rounded-2xl border border-slate-200/80 bg-white/90 shadow-2xs backdrop-blur-md">
        <div>
          <h2 className="text-base font-semibold text-slate-900">Truth Vault (version {kbVersion})</h2>
          <p className="mt-0.5 max-w-xl text-xs text-slate-500">
            Approved facts that every claim is checked against. When a fact changes, ClaimLoom re-indexes it and flags
            drafts that relied on the old value.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void refresh()}
            className="rounded-full border border-slate-200/80 bg-white px-3.5 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50 active:scale-95 transition-all"
          >
            ↺ Refresh
          </button>
          <button
            type="button"
            onClick={onSync}
            className="rounded-full bg-blue-600 px-4 py-1.5 text-xs font-semibold text-white shadow-xs hover:bg-blue-700 active:scale-95 transition-all"
          >
            Demo Price Change ($29 to $39) &amp; Sync
          </button>
          <button
            type="button"
            onClick={() => void resetDemo()}
            className="rounded-full border border-slate-200/80 bg-white px-3.5 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50 active:scale-95 transition-all"
          >
            Reset Demo Data
          </button>
        </div>
      </Card>

      {alert && (
        <div role="alert" className="flex items-center justify-between rounded-xl border border-red-200 bg-red-50/90 px-4 py-3 text-xs text-red-800 shadow-2xs backdrop-blur-md">
          <span>{alert}</span>
          <button type="button" onClick={() => setAlert("")} className="font-semibold text-red-900 hover:underline">
            Dismiss
          </button>
        </div>
      )}

      {affectedCount > 0 && (
        <div role="status" className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          The backend reports <strong>{affectedCount} scans</strong> affected. They are flagged for re-audit.
        </div>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-12">
        <Card className="space-y-3 p-5 lg:col-span-7 rounded-2xl border border-slate-200/80 bg-white/90 shadow-2xs backdrop-blur-md">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-semibold text-slate-900">Indexed facts</h3>
            <span className="text-xs font-medium text-slate-500">{chunks.length} verified facts</span>
          </div>
          {chunks.length === 0 ? (
            <div className="rounded-xl border border-dashed border-slate-200 p-8 text-center text-xs text-slate-500 bg-slate-50/50">
              No facts currently loaded. Click <strong className="text-slate-700">↺ Refresh</strong> or <strong className="text-slate-700">Reset Demo Data</strong> above to populate the Brand Truth Vault.
            </div>
          ) : (
            chunks.map((chunk) => (
              <div key={chunk.chunk_id} className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-4 shadow-2xs hover:bg-white hover:border-slate-300 transition-all">
                <div className="mb-2 flex items-center justify-between gap-2 text-xs">
                  <span className="font-semibold text-blue-700 bg-blue-50 px-2.5 py-0.5 rounded-full border border-blue-200/50">
                    {chunk.doc_title}, p.{chunk.page}
                  </span>
                  <span className="text-[11px] text-slate-400 font-mono">{chunk.updated_at ? String(chunk.updated_at).slice(0, 19).replace("T", " ") : ""}</span>
                </div>
                <textarea
                  aria-label={`Edit fact ${chunk.chunk_id}`}
                  defaultValue={chunk.fact_text}
                  onBlur={(e) => { if (e.currentTarget.value !== chunk.fact_text) void updateChunk(chunk, e.currentTarget.value); }}
                  className="w-full rounded-lg border border-slate-200 bg-white p-2.5 text-xs text-slate-800 leading-relaxed shadow-2xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 transition-all"
                />
              </div>
            ))
          )}
        </Card>

        <Card className="space-y-4 p-5 lg:col-span-5 rounded-2xl border border-slate-200/80 bg-white/90 shadow-2xs backdrop-blur-md">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-semibold text-slate-900">Brand rules</h3>
            <span className="text-xs font-medium text-slate-500">{rules.length} active</span>
          </div>
          <div className="max-h-64 space-y-2 overflow-y-auto pr-1">
            {rules.map((r) => (
              <div key={r.id} className="rounded-xl border border-slate-200/80 bg-slate-50/50 p-3 text-xs shadow-2xs hover:bg-white transition-all">
                <div className="flex justify-between gap-2 font-semibold text-slate-800">
                  <span>
                    #{r.id} {r.name}
                  </span>
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${r.severity === "High" ? "bg-red-50 text-red-700 border border-red-200/50" : "bg-amber-50 text-amber-700 border border-amber-200/50"}`}>{r.severity}</span>
                </div>
                <p className="mt-1 text-slate-500 leading-relaxed">{r.pattern}</p>
              </div>
            ))}
          </div>
          <div className="space-y-2 border-t border-slate-100 pt-4">
            <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">Add a rule</h4>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Rule title"
              aria-label="Rule title"
              className={inputCls}
            />
            <input
              type="text"
              value={pattern}
              onChange={(e) => setPattern(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && submit()}
              placeholder="What the rule requires or prohibits"
              aria-label="Rule guideline"
              className={inputCls}
            />
            <button type="button" onClick={submit} disabled={!ready || busy} className={`${btnPrimary} w-full`}>
              Save rule
            </button>
          </div>
        </Card>
      </div>
    </div>
  );
}

export default memo(VaultTab);
