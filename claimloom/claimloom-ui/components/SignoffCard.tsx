"use client";

import React, { memo, useEffect, useState } from "react";
import { Card } from "./Common";
import { btnDark, btnGhost, inputCls, Role } from "../lib/ui";
import { API_BASE, getAuthHeaders } from "../lib/api";

interface Props {
  role: Role;
  hint: string;
  canApprove: boolean;
  isApproved: boolean;
  onApprove: () => void;
  onViewCertificate: () => void;
  scanId?: string;
  onReaudit?: (needed: boolean, note?: string | null) => void;
}

interface Comment {
  id: string;
  author: string;
  text: string;
  time: string;
}

function SignoffCard({ role, hint, canApprove, isApproved, onApprove, onViewCertificate, scanId, onReaudit }: Props) {
  const [comments, setComments] = useState<Comment[]>([]);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    if (!scanId) { setComments([]); return; }
    let alive = true;
    const poll = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const response = await fetch(`${API_BASE}/api/scans/${encodeURIComponent(scanId)}/activity`, { headers: getAuthHeaders() });
        if (!response.ok) return;
        const data = await response.json();
        if (!alive) return;
        setComments((data.activity || []).filter((item: any) => item.type === "comment").map((item: any) => ({ id: String(item.comment_id || `${item.created_at}-${item.author_name}`), author: `${item.author_name} (${item.author_role})`, text: item.comment_text, time: item.created_at })));
        onReaudit?.(Boolean(data.reaudit?.needed), data.reaudit?.note);
      } catch { /* retry on the next poll */ }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 3000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [scanId, onReaudit]);

  const post = async () => {
    if (!draft.trim()) return;
    if (!scanId) return;
    try {
      const response = await fetch(`${API_BASE}/api/scans/${encodeURIComponent(scanId)}/comments`, { method: "POST", headers: getAuthHeaders({ "Content-Type": "application/json" }), body: JSON.stringify({ comment_text: draft.trim() }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Comment could not be posted");
      const c = data.comment;
      setComments((prev) => [...prev, { id: String(c.comment_id || Date.now()), author: `${c.author_name} (${c.author_role})`, text: c.comment_text, time: c.created_at }]);
      setDraft("");
    } catch (e) { window.alert(e instanceof Error ? e.message : "Comment could not be posted"); }
  };

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Sign-off</h2>
          <p className="text-xs text-slate-500">{hint}</p>
        </div>
        {isApproved ? (
          <button type="button" onClick={onViewCertificate} className={btnGhost}>
            View certificate
          </button>
        ) : (
          <button
            type="button"
            disabled={!canApprove}
            onClick={onApprove}
            className="inline-flex items-center rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-500"
          >
            {canApprove ? "Approve and sign" : "Approval locked"}
          </button>
        )}
      </div>

      <details className="mt-4 border-t border-slate-100 pt-4" open>
        <summary className="cursor-pointer text-sm font-semibold text-slate-700">
          Review thread ({comments.length})
        </summary>
        <div className="mt-3 max-h-44 space-y-2 overflow-y-auto">
          {comments.length === 0 && <p className="text-xs text-slate-500">No review comments yet on this scan.</p>}
          {comments.map((c) => (
            <div key={c.id} className="rounded-lg bg-slate-50 p-3 text-xs">
              <div className="mb-0.5 flex justify-between font-semibold text-slate-700">
                <span>{c.author}</span>
                <span className="font-normal text-slate-400">{c.time}</span>
              </div>
              <p className="text-slate-600">{c.text}</p>
            </div>
          ))}
        </div>
        <div className="mt-3 flex gap-2">
          <input
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void post()}
            placeholder={`Add a note as ${role}`}
            aria-label="Review note"
            className={inputCls}
          />
          <button type="button" onClick={() => void post()} className={btnDark}>
            Post
          </button>
        </div>
      </details>
    </Card>
  );
}

export default memo(SignoffCard);
