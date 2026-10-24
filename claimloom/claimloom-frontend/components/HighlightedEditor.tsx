"use client";
import { useRef } from "react";
import { toSegments } from "@/lib/highlight";
import { Issue } from "@/lib/schema";

interface EditorProps {
  text: string;
  issues: Issue[];
  setText: (val: string) => void;
  activeIssueId: string | null;
  onSelectIssue: (id: string) => void;
}

export default function HighlightedEditor({
  text,
  issues,
  setText,
  activeIssueId,
  onSelectIssue,
}: EditorProps) {
  const backdropRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const segments = toSegments(text, issues);

  const syncScroll = () => {
    if (backdropRef.current && textareaRef.current) {
      backdropRef.current.scrollTop = textareaRef.current.scrollTop;
      backdropRef.current.scrollLeft = textareaRef.current.scrollLeft;
    }
  };

  const handleCaretSelect = () => {
    const pos = textareaRef.current?.selectionStart ?? -1;
    if (pos < 0) return;
    let cur = 0;
    for (const seg of segments) {
      const next = cur + seg.text.length;
      if (seg.issue && pos >= cur && pos <= next) {
        onSelectIssue(seg.issue.id);
        return;
      }
      cur = next;
    }
  };

  return (
    <div className="relative w-full h-80 rounded-xl border border-slate-200 bg-slate-50/40 shadow-inner transition-all focus-within:bg-white focus-within:ring-2 focus-within:ring-indigo-500/20 focus-within:border-indigo-500 overflow-hidden">
      <div
        ref={backdropRef}
        aria-hidden="true"
        className="absolute inset-0 p-4 font-sans text-[15px] leading-relaxed whitespace-pre-wrap break-words overflow-y-auto pointer-events-none select-none text-transparent"
      >
        {segments.map((seg, i) => {
          if (!seg.issue) return <span key={i}>{seg.text}</span>;

          const isHigh = seg.issue.severity === "High";
          const isMedium = seg.issue.severity === "Medium";
          const isActive = seg.issue.id === activeIssueId;

          let bgClass = "bg-amber-200/60 border-b-2 border-amber-500";
          if (isHigh) bgClass = "bg-rose-200/70 border-b-2 border-rose-500";
          else if (isMedium) bgClass = "bg-amber-200/70 border-b-2 border-amber-500";

          if (isActive) {
            bgClass += " ring-2 ring-indigo-600/50";
          }

          return (
            <mark
              key={i}
              className={`rounded-[2px] text-transparent transition-colors ${bgClass}`}
            >
              {seg.text}
            </mark>
          );
        })}
        {"\u200b"}
      </div>

      <textarea
        ref={textareaRef}
        onScroll={syncScroll}
        onClick={handleCaretSelect}
        onKeyUp={handleCaretSelect}
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Paste marketing copy, ad text, or product claims here..."
        spellCheck={false}
        className="relative z-10 w-full h-full p-4 font-sans text-[15px] leading-relaxed bg-transparent text-slate-900 placeholder:text-slate-400 resize-none outline-none overflow-y-auto break-words"
      />
    </div>
  );
}