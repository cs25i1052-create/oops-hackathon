"use client";

import React, { memo, useEffect, useState } from "react";
import { Card } from "./Common";
import { btnDark, btnPrimary, Role } from "../lib/ui";
import { API_BASE, ensureSessionToken, getAuthHeaders } from "../lib/api";

interface Props { role: Role; }
function RadarTab({ role }: Props) {
  const [summary, setSummary] = useState<any>(null);
  const [rules, setRules] = useState<any[]>([]);
  const [proposals, setProposals] = useState<Record<number, any>>({});
  const [backtests, setBacktests] = useState<Record<number, any>>({});
  const [messages, setMessages] = useState<Record<number, string>>({});

  const refresh = async () => {
    try {
      const [s, a] = await Promise.all([fetch(`${API_BASE}/api/analytics/summary`, { headers: getAuthHeaders() }), fetch(`${API_BASE}/api/analytics/ambiguity`, { headers: getAuthHeaders() })]);
      if (!s.ok || !a.ok) throw new Error("Could not load governance analytics.");
      const sd = await s.json(), ad = await a.json();
      setSummary(sd); setRules(ad.ambiguity_radar || sd.ambiguity_radar || []);
    } catch (e) { setMessages({ 0: e instanceof Error ? e.message : "Analytics unavailable" }); }
  };
  useEffect(() => { void refresh(); }, []);

  const post = async (id: number, path: string, method = "POST", body?: unknown, requiredRole: "Reviewer" | "Admin" = "Reviewer") => {
    try {
      await ensureSessionToken(requiredRole);
      const response = await fetch(`${API_BASE}${path}`, { method, headers: getAuthHeaders({ "Content-Type": "application/json" }), ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data));
      return data;
    } catch (e) { setMessages((m) => ({ ...m, [id]: e instanceof Error ? e.message : "Request failed" })); return null; }
  };

  return <div className="space-y-6">
    <div className="flex justify-end"><button className={btnDark} onClick={() => void refresh()}>Refresh analytics</button></div>
    {messages[0] && <p role="alert" className="text-sm text-red-700">{messages[0]}</p>}
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">{[
      ["Total audits", summary?.total_scans], ["Average readiness", summary?.average_readiness_score], ["Approved scans", summary?.approved_scans], ["Re-audit queue", summary?.reaudit_queue_count], ["Rules version", summary?.rules_version],
    ].map(([label, value]) => <Card key={String(label)} className="p-4"><p className="text-xs text-slate-500">{label}</p><p className="mt-1 text-2xl font-bold">{value ?? "—"}</p></Card>)}</div>
    <div className="space-y-4">{rules.map((rule: any) => {
      const id = Number(rule.rule_id);
      const proposal = proposals[id];
      const bt = backtests[id];
      return <Card key={id} className="space-y-3 p-5">
        <div className="flex flex-wrap items-center justify-between gap-3"><div><h2 className="font-semibold">Rule #{id}: {rule.rule_cited}</h2><p className="text-sm text-slate-500">Flags {rule.total_flags} · Overrides {rule.override_count} ({rule.override_rate_percent}%) · Clarification: {rule.needs_clarification ? "needed" : "not flagged"}</p></div><button className={btnDark} onClick={async () => { const r = await post(id, `/api/rules/${id}/rewrite`); if (r) setProposals((p) => ({ ...p, [id]: r })); }}>Propose AI Rule Rewrite</button></div>
        {!!rule.sample_override_reasons?.length && <p className="text-xs text-slate-500">Reasons: {rule.sample_override_reasons.join(" · ")}</p>}
        {proposal && <div className="space-y-2 rounded bg-slate-50 p-3 text-sm"><p><b>Proposed rule:</b> {proposal.proposed_rule_text}</p><p><b>Regex:</b> {proposal.proposed_regex || "None"}</p><p><b>Rationale:</b> {proposal.suggestion?.rationale}</p><div className="flex gap-2"><button className={btnDark} onClick={async () => { const r = await post(id, `/api/rules/${id}/backtest`, "POST", { proposed_regex: proposal.proposed_regex }); if (r) setBacktests((v) => ({ ...v, [id]: r })); }}>Run Backtest</button><button className={btnPrimary} onClick={async () => { const r = await post(id, `/api/rules/${id}`, "PATCH", { rule_text: proposal.proposed_rule_text, regex_pattern: proposal.proposed_regex }, "Admin"); if (r) setMessages((m) => ({ ...m, [id]: `Committed version ${r.version_no}` })); }}>Commit Rule Update</button><button className={btnDark} onClick={async () => { const r = await post(id, `/api/rules/${id}/rollback`, "POST", {}, "Admin"); if (r) setMessages((m) => ({ ...m, [id]: `Restored version ${r.restored_version}` })); }}>Rollback</button></div></div>}
        {bt && <p className="text-xs text-slate-700">Evaluated {bt.scans_evaluated}; previous flags {bt.previous_flags}; new flags {bt.new_flags}; false positives eliminated {bt.false_positives_eliminated}; safety {bt.safety}.</p>}
        {messages[id] && <p role="status" className="text-xs text-blue-700">{messages[id]}</p>}
      </Card>;
    })}</div>
  </div>;
}
export default memo(RadarTab);
