"use client";

import React, { memo, useState } from "react";
import type { KBChunkItem } from "../lib/mockData";
import { Card } from "./Common";
import { BrandRule, btnPrimary, inputCls } from "../lib/ui";

interface Props {
  kbVersion: number;
  chunks: KBChunkItem[];
  affectedCount: number;
  onSync: () => void;
  rules: BrandRule[];
  onAddRule: (name: string, pattern: string) => void;
}

function VaultTab({ kbVersion, chunks, affectedCount, onSync, rules, onAddRule }: Props) {
  const [name, setName] = useState("");
  const [pattern, setPattern] = useState("");
  const ready = name.trim().length > 0 && pattern.trim().length > 0;

  const submit = () => {
    if (!ready) return;
    onAddRule(name.trim(), pattern.trim());
    setName("");
    setPattern("");
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
        <button type="button" onClick={onSync} className={btnPrimary}>
          Simulate price change ($29 to $39)
        </button>
      </Card>

      {affectedCount > 0 && (
        <div role="status" className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          Updating fact #3 affected <strong>{affectedCount} approved drafts</strong>. They are flagged for re-audit.
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
              <p className="text-sm text-slate-700">{chunk.fact_text}</p>
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
            <button type="button" onClick={submit} disabled={!ready} className={`${btnPrimary} w-full`}>
              Save rule
            </button>
          </div>
        </Card>
      </div>
    </div>
  );
}

export default memo(VaultTab);