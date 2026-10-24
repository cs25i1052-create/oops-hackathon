"use client";
import { useState } from "react";

interface ManagerBarProps {
  unresolvedHighCount: number;
  overriddenHighCount: number;
  onAcknowledgeOverrides: () => void;
  totalIssuesCount: number;
  hasScanned: boolean;
  readinessScore?: number;
}

export default function ManagerBar({
  unresolvedHighCount,
  overriddenHighCount,
  onAcknowledgeOverrides,
  totalIssuesCount,
  hasScanned,
  readinessScore,
}: ManagerBarProps) {
  const [status, setStatus] = useState<"pending" | "approved" | "rejected">("pending");
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [rejectNote, setRejectNote] = useState("");

  const totalBlockers = unresolvedHighCount + overriddenHighCount;

  const updateDecision = (newStatus: "pending" | "approved" | "rejected", note = "") => {
    setStatus(newStatus);
    setShowRejectInput(false);
    localStorage.setItem("claimloom_manager_status", newStatus);
    localStorage.setItem("claimloom_manager_note", note);
  };

  if (status === "approved") {
    return (
      <div className="mt-4 bg-emerald-50 border border-emerald-200 rounded-xl p-4 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-3">
          <span className="w-8 h-8 rounded-full bg-emerald-600 text-white flex items-center justify-center font-bold text-sm">
            ✓
          </span>
          <div>
            <p className="text-sm font-bold text-emerald-950">
              Approved for Publication
            </p>
            <p className="text-xs text-emerald-700">
              Governance gate passed {readinessScore !== undefined && `• Score: ${readinessScore}/100`}
            </p>
          </div>
        </div>
        <button
          onClick={() => updateDecision("pending")}
          className="text-xs font-semibold text-emerald-800 hover:underline cursor-pointer"
        >
          Revoke
        </button>
      </div>
    );
  }

  if (status === "rejected") {
    return (
      <div className="mt-4 bg-rose-50 border border-rose-200 rounded-xl p-4 flex items-center justify-between shadow-sm">
        <div>
          <span className="text-[11px] font-bold uppercase tracking-wider text-rose-700 bg-rose-100 px-2 py-0.5 rounded">
            Changes Requested
          </span>
          <p className="text-sm font-medium text-rose-900 mt-1.5">
            &ldquo;{rejectNote || "Please resolve flagged compliance issues before publishing."}&rdquo;
          </p>
        </div>
        <button
          onClick={() => updateDecision("pending")}
          className="text-xs font-semibold text-rose-700 hover:underline shrink-0 ml-4 cursor-pointer"
        >
          Reset Review
        </button>
      </div>
    );
  }

  return (
    <div className="mt-4 bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">
          Manager Sign-Off Gate {readinessScore !== undefined && `(Readiness: ${readinessScore}%)`}
        </span>
        {unresolvedHighCount > 0 ? (
          <span className="text-xs font-semibold text-rose-600">
            🔒 {unresolvedHighCount} High-Severity Blocker{unresolvedHighCount > 1 ? "s" : ""}
          </span>
        ) : overriddenHighCount > 0 ? (
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-amber-700">
              ⚠️ {overriddenHighCount} High Overridden by Author
            </span>
            <button
              onClick={onAcknowledgeOverrides}
              className="text-[11px] font-bold text-indigo-600 hover:underline cursor-pointer"
            >
              Acknowledge
            </button>
          </div>
        ) : (
          <span className="text-xs font-semibold text-emerald-600">
            ✓ Zero Critical Blockers
          </span>
        )}
      </div>

      {showRejectInput ? (
        <div className="space-y-2">
          <input
            type="text"
            value={rejectNote}
            onChange={(e) => setRejectNote(e.target.value)}
            placeholder="Add reviewer note..."
            className="w-full text-xs p-2.5 border border-slate-300 rounded-lg outline-none focus:border-indigo-500"
          />
          <div className="flex gap-2">
            <button
              onClick={() => updateDecision("rejected", rejectNote)}
              className="flex-1 bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold py-2 rounded-lg transition cursor-pointer"
            >
              Confirm Rejection
            </button>
            <button
              onClick={() => setShowRejectInput(false)}
              className="px-3 py-2 bg-slate-100 text-slate-600 text-xs font-semibold rounded-lg cursor-pointer"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex gap-3">
          <button
            onClick={() => updateDecision("approved")}
            disabled={!hasScanned || totalBlockers > 0}
            className="flex-1 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-200 disabled:text-slate-400 disabled:cursor-not-allowed text-white text-xs font-semibold py-2.5 rounded-lg transition shadow-sm cursor-pointer"
          >
            Approve Asset ({totalIssuesCount} flags remaining)
          </button>
          <button
            onClick={() => setShowRejectInput(true)}
            disabled={!hasScanned}
            className="px-4 py-2.5 border border-rose-200 text-rose-600 hover:bg-rose-50 disabled:opacity-40 disabled:cursor-not-allowed text-xs font-semibold rounded-lg transition cursor-pointer"
          >
            Request Changes
          </button>
        </div>
      )}
    </div>
  );
}