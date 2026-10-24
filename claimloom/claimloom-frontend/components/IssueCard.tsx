"use client";
import { Issue } from "@/lib/schema";

interface IssueCardProps {
  issue: Issue;
  isActive?: boolean;
  onAccept: (issue: Issue) => void;
  onDismiss: (issue: Issue) => void;
}

export default function IssueCard({
  issue,
  isActive,
  onAccept,
  onDismiss,
}: IssueCardProps) {
  const severityStyles = {
    High: {
      border: "border-l-rose-500",
      badge: "bg-rose-50 text-rose-700 border-rose-200",
      dot: "bg-rose-500",
    },
    Medium: {
      border: "border-l-amber-500",
      badge: "bg-amber-50 text-amber-700 border-amber-200",
      dot: "bg-amber-500",
    },
    Low: {
      border: "border-l-slate-400",
      badge: "bg-slate-100 text-slate-700 border-slate-200",
      dot: "bg-slate-400",
    },
  }[issue.severity];

  const isVisual = issue.violation_type === "Visual";

  return (
    <div
      id={`issue-${issue.id}`}
      className={`group rounded-xl border border-slate-200 border-l-4 ${severityStyles.border} bg-white p-4 transition-all duration-200 ${
        isActive
          ? "ring-2 ring-indigo-500/40 shadow-md -translate-y-0.5"
          : "shadow-sm hover:shadow-md hover:-translate-y-0.5"
      }`}
    >
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-bold uppercase tracking-wider border ${severityStyles.badge}`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${severityStyles.dot}`} />
            {issue.severity}
          </span>
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 bg-slate-100 px-2 py-0.5 rounded-md">
            {issue.violation_type}
          </span>
        </div>

        {issue.confidence !== undefined && (
          <span className="text-[11px] font-medium text-slate-400">
            {Math.round(issue.confidence * 100)}% match
          </span>
        )}
      </div>

      <div className="text-sm leading-snug space-y-1.5 my-3">
        <div className="flex items-start gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400 mt-0.5 shrink-0">
            {isVisual ? "Issue:" : "Found:"}
          </span>
          <span
            className={`font-medium px-1.5 py-0.5 rounded ${
              isVisual
                ? "bg-rose-50 text-rose-900"
                : "line-through bg-rose-50 text-rose-800 decoration-rose-400"
            }`}
          >
            {issue.flagged_text}
          </span>
        </div>

        <div className="flex items-start gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-emerald-600 mt-0.5 shrink-0">
            Fix:
          </span>
          <span className="font-medium bg-emerald-50 text-emerald-900 border border-emerald-200/60 px-1.5 py-0.5 rounded">
            {issue.suggested_fix}
          </span>
        </div>
      </div>

      <div className="mt-3 p-2.5 rounded-lg bg-slate-50 border border-slate-100 text-xs text-slate-600 leading-relaxed space-y-1">
        <div>
          <span className="font-semibold text-slate-800">Rule: </span>
          {issue.rule_cited}
        </div>
        {issue.explanation && (
          <div className="text-slate-500">{issue.explanation}</div>
        )}
      </div>

      <div className="mt-4 flex items-center gap-2 pt-2 border-t border-slate-100">
        <button
          onClick={() => onAccept(issue)}
          className="flex-1 bg-slate-900 hover:bg-indigo-600 text-white text-xs font-semibold py-2 px-3 rounded-lg transition-colors cursor-pointer"
        >
          {isVisual ? "Mark Resolved" : "Apply Suggested Fix"}
        </button>
        <button
          onClick={() => onDismiss(issue)}
          className="px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-600 text-xs font-semibold rounded-lg transition-colors cursor-pointer"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}