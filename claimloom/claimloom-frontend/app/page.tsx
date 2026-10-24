"use client";
import { useState, useRef } from "react";
import { Issue } from "@/lib/schema";
import { scanText, scanImage } from "@/lib/api";
import HighlightedEditor from "@/components/HighlightedEditor";
import IssueCard from "@/components/IssueCard";
import ImageUploader from "@/components/ImageUploader";
import ManagerBar from "@/components/ManagerBar";

const GOLDEN_PATH_DRAFT =
  "Get our software for guaranteed 100% results. It is cheap, fast, and outperforms every competitor on the market.";

function applyFix(text: string, issue: Issue): string {
  const s = issue.start ?? -1;
  const e = issue.end ?? -1;
  const exactMatch = s >= 0 && e > s && text.slice(s, e) === issue.flagged_text;
  const idx = exactMatch ? s : text.indexOf(issue.flagged_text);
  if (idx < 0) return text;
  return (
    text.slice(0, idx) +
    issue.suggested_fix +
    text.slice(idx + issue.flagged_text.length)
  );
}

interface UndoSnapshot {
  text: string;
  textIssues: Issue[];
  overriddenHigh: number;
}

export default function ClaimLoomPage() {
  const [activeTab, setActiveTab] = useState<"text" | "image">("text");
  const [draftText, setDraftText] = useState(GOLDEN_PATH_DRAFT);
  const [undo, setUndo] = useState<UndoSnapshot | null>(null);

  const [textIssues, setTextIssues] = useState<Issue[]>([]);
  const [imageIssues, setImageIssues] = useState<Issue[]>([]);
  const [overriddenHighCount, setOverriddenHighCount] = useState(0);
  const [scanCount, setScanCount] = useState(0);
  const [readinessScore, setReadinessScore] = useState<number | undefined>(undefined);
  const [aiDisclosure, setAiDisclosure] = useState<string | undefined>(undefined);

  const [isScanning, setIsScanning] = useState(false);
  const [isColdStart, setIsColdStart] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeIssueId, setActiveIssueId] = useState<string | null>(null);

  const [forceMock, setForceMock] = useState(
    process.env.NEXT_PUBLIC_USE_MOCK === "true"
  );

  const abortRef = useRef<AbortController | null>(null);
  const lastFileRef = useRef<File | null>(null);

  const runScan = async (
    mode: "text" | "image",
    file?: File,
    mockOverride = forceMock
  ) => {
    if (file) lastFileRef.current = file;
    if (mode === "image" && !lastFileRef.current) {
      setError("Please select an image asset to scan first.");
      return;
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsScanning(true);
    setIsColdStart(false);
    setError(null);

    const coldTimer = setTimeout(() => {
      if (abortRef.current === controller) setIsColdStart(true);
    }, 5000);

    try {
      const combinedSignal = AbortSignal.any([
        controller.signal,
        AbortSignal.timeout(90000),
      ]);

      const response =
        mode === "text"
          ? await scanText(draftText, mockOverride, combinedSignal)
          : await scanImage(lastFileRef.current!, mockOverride, combinedSignal);

      if (abortRef.current !== controller) return;

      if (response.readiness_score !== undefined) setReadinessScore(response.readiness_score);
      if (response.ai_disclosure) setAiDisclosure(response.ai_disclosure);

      if (mode === "text") {
        setTextIssues(response.issues);
        setUndo(null);
      } else {
        setImageIssues(response.issues);
      }

      setOverriddenHighCount(0);
      setScanCount((c) => c + 1);
    } catch (err: unknown) {
      if (abortRef.current !== controller) return;
      if (err instanceof Error && err.name !== "AbortError") {
        setError(
          err.message ||
            "Could not reach the compliance engine. Check backend CORS or switch to Mock Mode."
        );
      }
    } finally {
      clearTimeout(coldTimer);
      if (abortRef.current === controller) {
        setIsScanning(false);
        setIsColdStart(false);
      }
    }
  };

  const handleAcceptFix = (issue: Issue) => {
    if (issue.violation_type === "Visual") {
      setImageIssues((prev) => prev.filter((i) => i.id !== issue.id));
    } else {
      setUndo({
        text: draftText,
        textIssues,
        overriddenHigh: overriddenHighCount,
      });
      setDraftText((prev) => applyFix(prev, issue));
      setTextIssues((prev) => prev.filter((i) => i.id !== issue.id));
    }
  };

  const handleDismiss = (issue: Issue) => {
    if (issue.severity === "High") {
      setOverriddenHighCount((c) => c + 1);
    }
    if (issue.violation_type === "Visual") {
      setImageIssues((prev) => prev.filter((i) => i.id !== issue.id));
    } else {
      setUndo({
        text: draftText,
        textIssues,
        overriddenHigh: overriddenHighCount,
      });
      setTextIssues((prev) => prev.filter((i) => i.id !== issue.id));
    }
  };

  const visibleIssues = activeTab === "text" ? textIssues : imageIssues;
  const allIssues = [...textIssues, ...imageIssues];
  const unresolvedHighCount = allIssues.filter((i) => i.severity === "High").length;
  const hasScanned = scanCount > 0;

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 font-sans">
      <header className="bg-white border-b border-slate-200 sticky top-0 z-30">
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-bold shadow-sm">
              C
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight text-slate-900 leading-none">
                ClaimLoom
              </h1>
              <p className="text-[11px] font-medium text-slate-500 mt-0.5">
                Pre-Publication Brand Governance Gatekeeper
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {readinessScore !== undefined && (
              <span className="text-xs font-bold px-3 py-1 bg-indigo-50 text-indigo-700 rounded-lg border border-indigo-100">
                Readiness Score: {readinessScore}%
              </span>
            )}
            <button
              onClick={() => setForceMock((m) => !m)}
              className={`text-xs font-semibold px-3 py-1.5 rounded-full border transition cursor-pointer ${
                forceMock
                  ? "bg-amber-50 text-amber-800 border-amber-200"
                  : "bg-emerald-50 text-emerald-800 border-emerald-200"
              }`}
            >
              {forceMock ? "⚡ Mode: Mock Contract V2" : "🟢 Mode: Live FastAPI"}
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8 grid grid-cols-1 lg:grid-cols-12 gap-8">
        <section className="lg:col-span-7 flex flex-col">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 flex-1 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between border-b border-slate-200 pb-4 mb-5">
                <div className="flex gap-2">
                  <button
                    onClick={() => setActiveTab("text")}
                    className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
                      activeTab === "text"
                        ? "bg-slate-900 text-white"
                        : "text-slate-600 hover:bg-slate-100"
                    }`}
                  >
                    Text Copy Check ({textIssues.length})
                  </button>
                  <button
                    onClick={() => setActiveTab("image")}
                    className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer ${
                      activeTab === "image"
                        ? "bg-slate-900 text-white"
                        : "text-slate-600 hover:bg-slate-100"
                    }`}
                  >
                    Visual Asset Check ({imageIssues.length})
                  </button>
                </div>

                {activeTab === "text" && (
                  <div className="flex items-center gap-3">
                    {undo && (
                      <button
                        onClick={() => {
                          setDraftText(undo.text);
                          setTextIssues(undo.textIssues);
                          setOverriddenHighCount(undo.overriddenHigh);
                          setUndo(null);
                        }}
                        className="text-xs font-semibold text-indigo-600 hover:underline cursor-pointer"
                      >
                        ↩ Undo Last Action
                      </button>
                    )}
                    <button
                      onClick={() => {
                        setDraftText(GOLDEN_PATH_DRAFT);
                        setUndo(null);
                      }}
                      className="text-xs font-medium text-slate-500 hover:text-slate-800 cursor-pointer"
                    >
                      Load Golden Sample
                    </button>
                  </div>
                )}
              </div>

              {activeTab === "text" ? (
                <>
                  <HighlightedEditor
                    text={draftText}
                    setText={setDraftText}
                    issues={textIssues}
                    activeIssueId={activeIssueId}
                    onSelectIssue={(id) => {
                      setActiveIssueId(id);
                      document.getElementById(`issue-${id}`)?.scrollIntoView({
                        behavior: "smooth",
                        block: "nearest",
                      });
                    }}
                  />
                  <div className="mt-3 flex justify-between items-center text-xs text-slate-400">
                    <span>Click any highlighted phrase to jump to its rule</span>
                    <span>{draftText.length} characters</span>
                  </div>
                </>
              ) : (
                <ImageUploader
                  onScan={(file) => runScan("image", file)}
                  isScanning={isScanning}
                />
              )}
            </div>

            {activeTab === "text" && (
              <button
                onClick={() => runScan("text")}
                disabled={isScanning || !draftText.trim()}
                className={`mt-6 w-full py-3.5 rounded-xl font-semibold text-sm text-white shadow-sm transition cursor-pointer ${
                  isScanning
                    ? "bg-indigo-600 animate-pulse"
                    : "bg-slate-900 hover:bg-slate-800 disabled:bg-slate-300"
                }`}
              >
                {isScanning
                  ? isColdStart
                    ? "Waking up AI Engine on Render (Cold Start)..."
                    : "Auditing Draft Against Brand Vault..."
                  : "Run Brand Compliance Audit"}
              </button>
            )}
          </div>
        </section>

        <section className="lg:col-span-5 flex flex-col h-[38rem]">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 flex-1 flex flex-col overflow-hidden">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-100">
              <div>
                <h2 className="text-base font-bold text-slate-900">
                  Compliance Audit Feed
                </h2>
                <p className="text-xs text-slate-500">
                  {aiDisclosure || "Explainable citations & non-destructive rewrites"}
                </p>
              </div>
              {hasScanned && !isScanning && (
                <span className="text-xs font-bold px-2.5 py-1 rounded-full bg-slate-100 text-slate-700">
                  {visibleIssues.length} {visibleIssues.length === 1 ? "Flag" : "Flags"}
                </span>
              )}
            </div>

            <div className="flex-1 overflow-y-auto pr-1 space-y-3">
              {isScanning && (
                <div className="space-y-3 py-2">
                  {isColdStart && (
                    <div className="p-3 rounded-lg bg-indigo-50 border border-indigo-100 text-xs text-indigo-800 font-medium">
                      ⏳ Free-tier backend is waking from sleep. Hang tight (~15-30s)...
                    </div>
                  )}
                  {[1, 2].map((n) => (
                    <div
                      key={n}
                      className="p-4 rounded-xl border border-slate-200 bg-slate-50/70 animate-pulse space-y-3"
                    >
                      <div className="flex justify-between">
                        <div className="h-4 w-20 bg-slate-200 rounded" />
                        <div className="h-4 w-14 bg-slate-200 rounded" />
                      </div>
                      <div className="h-4 w-3/4 bg-slate-200 rounded" />
                      <div className="h-10 w-full bg-slate-200 rounded" />
                    </div>
                  ))}
                </div>
              )}

              {!isScanning && error && (
                <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-900 space-y-3">
                  <p className="text-xs font-bold uppercase tracking-wider text-rose-700">
                    Backend Connection Error
                  </p>
                  <p className="text-xs leading-relaxed">{error}</p>
                  <div className="flex gap-2">
                    <button
                      onClick={() => runScan(activeTab, undefined, forceMock)}
                      className="px-3 py-1.5 bg-rose-600 text-white text-xs font-semibold rounded-lg cursor-pointer"
                    >
                      Retry Scan
                    </button>
                    <button
                      onClick={() => {
                        setForceMock(true);
                        runScan(activeTab, undefined, true);
                      }}
                      className="px-3 py-1.5 bg-white border border-rose-300 text-rose-800 text-xs font-semibold rounded-lg cursor-pointer"
                    >
                      Switch to Mock Mode
                    </button>
                  </div>
                </div>
              )}

              {!isScanning && !error && !hasScanned && (
                <div className="h-full flex flex-col items-center justify-center text-center px-6 text-slate-400">
                  <div className="w-14 h-14 rounded-2xl bg-slate-100 flex items-center justify-center mb-3 text-slate-400">
                    <svg className="w-7 h-7" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={1.5}
                        d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
                      />
                    </svg>
                  </div>
                  <p className="text-sm font-semibold text-slate-600">
                    Brand Vault Ready
                  </p>
                  <p className="text-xs text-slate-400 mt-1">
                    Run a scan on your copy or visual asset to verify tone, claims, and WCAG accessibility.
                  </p>
                </div>
              )}

              {!isScanning && !error && hasScanned && visibleIssues.length === 0 && (
                <div className="h-full flex flex-col items-center justify-center text-center px-6">
                  <div className="w-12 h-12 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center mb-3 font-bold text-lg">
                    ✓
                  </div>
                  <p className="text-sm font-bold text-slate-800">
                    No Flags Remaining
                  </p>
                  <p className="text-xs text-slate-500 mt-1">
                    All issues in this tab are resolved. Check the Manager Gate below for publication status.
                  </p>
                </div>
              )}

              {!isScanning &&
                !error &&
                visibleIssues.map((issue) => (
                  <div
                    key={issue.id}
                    onMouseEnter={() => setActiveIssueId(issue.id)}
                    onMouseLeave={() => setActiveIssueId(null)}
                  >
                    <IssueCard
                      issue={issue}
                      isActive={activeIssueId === issue.id}
                      onAccept={handleAcceptFix}
                      onDismiss={handleDismiss}
                    />
                  </div>
                ))}
            </div>
          </div>

          <ManagerBar
            key={scanCount}
            unresolvedHighCount={unresolvedHighCount}
            overriddenHighCount={overriddenHighCount}
            onAcknowledgeOverrides={() => setOverriddenHighCount(0)}
            totalIssuesCount={allIssues.length}
            hasScanned={hasScanned}
            readinessScore={readinessScore}
          />
        </section>
      </main>
    </div>
  );
}