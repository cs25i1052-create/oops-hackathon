"use client";

import React, { memo, useState } from "react";
import { Card } from "./Common";
import { btnDark, btnGhost, inputCls, Role } from "../lib/ui";

interface Props {
  role: Role;
  hint: string;
  canApprove: boolean;
  isApproved: boolean;
  onApprove: () => void;
  onViewCertificate: () => void;
}

interface Comment {
  id: string;
  author: string;
  text: string;
  time: string;
}

function SignoffCard({ role, hint, canApprove, isApproved, onApprove, onViewCertificate }: Props) {
  const [comments, setComments] = useState<Comment[]>([
    {
      id: "c1",
      author: "Senior Legal Reviewer",
      text: "Please update the Pro Plan price to $29/month and remove the absolute guarantee before final sign-off.",
      time: "5 mins ago",
    },
  ]);
  const [draft, setDraft] = useState("");

  const post = () => {
    if (!draft.trim()) return;
    setComments((prev) => [
      ...prev,
      { id: `c_${Date.now()}`, author: `${role} (you)`, text: draft.trim(), time: "Just now" },
    ]);
    setDraft("");
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
            onKeyDown={(e) => e.key === "Enter" && post()}
            placeholder={`Add a note as ${role}`}
            aria-label="Review note"
            className={inputCls}
          />
          <button type="button" onClick={post} className={btnDark}>
            Post
          </button>
        </div>
      </details>
    </Card>
  );
}

export default memo(SignoffCard);