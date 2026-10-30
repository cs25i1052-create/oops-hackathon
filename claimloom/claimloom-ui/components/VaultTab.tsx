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
      if (!ruleRes.ok || !kbRes.ok) throw new Error("Could not load live Truth Vault data.");
      const [ruleData, kbData] = await Promise.all([ruleRes.json() as Promise<RulesResponse>, kbRes.json() as Promise<SourcesResponse>]);
      const mappedRules: BrandRule[] = (ruleData.rules || []).map((r) => ({ id: r.rule_id, name: r.rule_cited, category: r.violation_type, severity: r.severity, pattern: r.rule_text }));
      const mappedChunks: KBChunkItem[] = (kbData.chunks || []).map((c) => ({ chunk_id: c.chunk_id, doc_title: c.doc_title, page: c.page_num, category: "Knowledge Base", fact_text: c.chunk_text, updated_at: c.updated_at || "" }));
      dataLoadedRef.current?.(mappedRules, mappedChunks, ruleData.rules_version || 1, kbData.kb_version || 1);
    } catch (e) { setAlert(e instanceof Error ? e.message : "Refresh failed"); }
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
      if (!response.ok) throw new Error("Reset failed");
      await refresh();
    } catch (e) { setAlert(e instanceof Error ? e.message : "Reset failed"); }
  };

  return (
    <div className="space-y-6">
      <Card className="flex flex-wrap items-center justify-between gap-4 p-5">
        <div>
          <h2 className="text-base font-semibold">Truth Vault (version {kbVersion})</h2>
          <p className="mt-0.5 max-w-xl text-sm text-slate-500">
            Approved facts that every claim is checked against. When a fact changes, ClaimLoom re-indexes it and flags
            drafts that relied on the old value.
          </p>
        </div>
        <div className="flex gap-2"><button type="button" onClick={() => void refresh()} className={btnPrimary}>Refresh</button><button type="button" onClick={onSync} className={btnPrimary}>
          Demo Price Change ($29 to $39) &amp; Sync
        </button><button type="button" onClick={() => void resetDemo()} className={btnPrimary}>Reset Demo Data
        </button>
        </div>
      </Card>

      {alert && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 p-3 text-sm text-red-800">{alert}</div>}

      {affectedCount > 0 && (
        <div role="status" className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          The backend reports <strong>{affectedCount} scans</strong> affected. They are flagged for re-audit.
        </div>
      )}

      <div className="grid items-start gap-6 lg:grid-cols-12">
        <Card className="space-y-3 p-5 lg:col-span-7">
          <h3 className="text-base font-semibold">Indexed facts</h3>
          {chunks.map((chunk) => (
            <div key={chunk.chunk_id} className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="mb-1 flex items-center justify-between gap-2 text-xs">
                <span className="font-semibold text-blue-700">
                  {chunk.doc_title}, p.{chunk.page}
                </span>
                <span className="text-slate-400">{chunk.updated_at}</span>
              </div>
              <textarea aria-label={`Edit fact ${chunk.chunk_id}`} defaultValue={chunk.fact_text} onBlur={(e) => { if (e.currentTarget.value !== chunk.fact_text) void updateChunk(chunk, e.currentTarget.value); }} className="w-full rounded border p-2 text-sm text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600" />
            </div>
          ))}
        </Card>

        <Card className="space-y-4 p-5 lg:col-span-5">
          <h3 className="text-base font-semibold">Brand rules</h3>
          <div className="max-h-64 space-y-2 overflow-y-auto">
            {rules.map((r) => (
              <div key={r.id} className="rounded-lg border border-slate-200 p-3 text-xs">
                <div className="flex justify-between gap-2 font-semibold text-slate-800">
                  <span>
                    #{r.id} {r.name}
                  </span>
                  <span className={r.severity === "High" ? "text-red-600" : "text-amber-600"}>{r.severity}</span>
                </div>
                <p className="mt-1 text-slate-500">{r.pattern}</p>
              </div>
            ))}
          </div>
          <div className="space-y-2 border-t border-slate-200 pt-4">
            <h4 className="text-sm font-semibold text-slate-700">Add a rule</h4>
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
