"use client";

import React, { memo } from "react";
import { Card } from "./Common";
import { btnDark } from "../lib/ui";

const METRICS = [
  { label: "Audits logged", value: "142", note: "All PII redacted", noteCls: "text-emerald-700", valCls: "text-slate-900" },
  { label: "Mean readiness", value: "81.4", note: "+14% since KB v1", noteCls: "text-blue-700", valCls: "text-slate-900" },
  { label: "Top override rate", value: "Rule #3, 38%", note: "Flagged as ambiguous", noteCls: "text-amber-700", valCls: "text-amber-600" },
  { label: "Median latency", value: "410 ms", note: "Cached scans: 18 ms", noteCls: "text-slate-500", valCls: "text-slate-900" },
];

interface Props {
  ruleOptimized: boolean;
  onOptimize: () => void;
}

function RadarTab({ ruleOptimized, onOptimize }: Props) {
  return (
    <div className="space-y-6">
      <p className="text-sm text-slate-500">Sample metrics from the demo workspace.</p>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {METRICS.map((m) => (
          <Card key={m.label} className="p-5">
            <p className="text-xs font-medium text-slate-500">{m.label}</p>
            <p className={`mt-1 text-2xl font-bold ${m.valCls}`}>{m.value}</p>
            <p className={`text-xs font-medium ${m.noteCls}`}>{m.note}</p>
          </Card>
        ))}
      </div>

      <Card className="p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-800">
              Ambiguity alert: 38% of reviewers override this rule
            </span>
            <h2 className="mt-3 text-base font-semibold">Self-healing rule optimizer for Rule #3</h2>
            <p className="mt-1 max-w-xl text-sm text-slate-500">
              Reviewers often override Rule #3 when copy cites certified SLA percentages. The optimizer rewrites the
              rule, backtests it on past audits, and commits it if it holds up.
            </p>
          </div>
          <button type="button" disabled={ruleOptimized} onClick={onOptimize} className={btnDark}>
            {ruleOptimized ? "Committed" : "Backtest and commit rewrite"}
          </button>
        </div>
        <div className="mt-4 rounded-lg bg-slate-50 p-4 text-sm">
          <p className="font-semibold text-slate-900">Rule #3 status</p>
          <p className="mt-1 text-slate-600">
            {ruleOptimized
              ? "Optimized (v2). The rule now excludes verified enterprise SLA claims such as the 99.9% uptime SLA."
              : "Baseline (v1). Run the optimizer to apply the self-healing rewrite."}
          </p>
        </div>
      </Card>
    </div>
  );
}

export default memo(RadarTab);