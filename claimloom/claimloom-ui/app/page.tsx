"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { runTextScan, uploadAssetForScan, syncScanIdToUrl } from "../lib/api";
import { approveScan, fetchScan, waitForEngine, withColdStartRetry } from "../lib/client";
import {
  MOCK_SCAN_RESPONSE_V3,
  MOCK_CLEAN_SCAN_V3,
  SAMPLE_VIOLATION_TEXT,
  SAMPLE_CLEAN_TEXT,
  INITIAL_KB_CHUNKS,
} from "../lib/mockData";
import type { KBChunkItem } from "../lib/mockData";
import { ScanResponse, ScanResponseSchema, Issue } from "../lib/schema";
import { BrandRule, Origin, Role, Tab, btnGhost, calcScore, errMsg, resolveRange, selectCls } from "../lib/ui";

import EditorCard, { MAX_CHARS } from "../components/EditorCard";
import SignoffCard from "../components/SignoffCard";
import ResultsPanel from "../components/ResultsPanel";
import CanvasTab from "../components/CanvasTab";
import VaultTab from "../components/VaultTab";
import RadarTab from "../components/RadarTab";
import CertificateModal from "../components/CertificateModal";

const MAX_UPLOAD = 5 * 1024 * 1024;
const MIN_CHARS = 10;
const DEMO_SIGNATURE =
  "ed25519:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08";

const TABS: { id: Tab; label: string }[] = [
  { id: "studio", label: "Studio" },
  { id: "canvas", label: "Canvas" },
  { id: "vault", label: "Truth Vault" },
  { id: "radar", label: "Governance Radar" },
];

const INITIAL_RULES: BrandRule[] = [
  { id: 1, name: "ClaimLoom Exact Capitalization", category: "Terminology", severity: "Medium", pattern: "Always spell 'ClaimLoom' with capital C and capital L." },
  { id: 3, name: "No Unsubstantiated 100% Guarantees", category: "Tone", severity: "High", pattern: "Prohibit 'guaranteed 100%', 'zero risk', or 'instant results'." },
  { id: 5, name: "Pro Plan Pricing Accuracy ($29/mo)", category: "Factual", severity: "High", pattern: "Must cite $29/month or $290/year per Approved_Pricing_Policy.md." },
];

function buildOfflineTextScan(text: string): ScanResponse {
  const lower = text.toLowerCase();
  const looksViolating = lower.includes("$15/month") || lower.includes("guaranteed 100%");
  const base = looksViolating ? MOCK_SCAN_RESPONSE_V3 : MOCK_CLEAN_SCAN_V3;
  const issues = base.issues.filter((i) => i.flagged_text && lower.includes(i.flagged_text.toLowerCase()));
  return {
    ...base,
    scan_id: `scan_${Math.random().toString(36).slice(2, 8)}`,
    input_type: "text",
    redacted_text: text,
    issues,
    readiness_score: issues.length === base.issues.length ? base.readiness_score : calcScore(issues),
  };
}

export default function ClaimLoomWorkspace() {
  const [activeTab, setActiveTab] = useState<Tab>("studio");
  const [role, setRole] = useState<Role>("Reviewer");
  const [workspaceId, setWorkspaceId] = useState<"default" | "custom">("default");
  const [channel, setChannel] = useState("general");

  const [engineOnline, setEngineOnline] = useState(false);
  const [isWakingUp, setIsWakingUp] = useState(true);
  const [kbVersion, setKbVersion] = useState(1);
  const [rulesVersion, setRulesVersion] = useState(1);

  const [editorText, setEditorText] = useState("");
  const [originalText, setOriginalText] = useState("");
  const [isScanning, setIsScanning] = useState(false);
  const [scanStep, setScanStep] = useState("");
  const [scanResult, setScanResult] = useState<ScanResponse | null>(null);
  const [scanOrigin, setScanOrigin] = useState<Origin>("sample");
  const [selectedIssueId, setSelectedIssueId] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [errorBanner, setErrorBanner] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const [showCert, setShowCert] = useState(false);
  const [signature, setSignature] = useState<{ value: string; live: boolean }>({
    value: DEMO_SIGNATURE,
    live: false,
  });

  const [kbChunks, setKbChunks] = useState<KBChunkItem[]>(INITIAL_KB_CHUNKS);
  const [affectedScansCount, setAffectedScansCount] = useState(0);
  const [ruleOptimized, setRuleOptimized] = useState(false);
  const [rules, setRules] = useState<BrandRule[]>(INITIAL_RULES);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestId = useRef(0);
  const wakingRef = useRef(true);
  const editorRef = useRef("");
  const scanRef = useRef<ScanResponse | null>(null);
  const originRef = useRef<Origin>("sample");
  const roleRef = useRef<Role>("Reviewer");

  useEffect(() => {
    editorRef.current = editorText;
    scanRef.current = scanResult;
    originRef.current = scanOrigin;
    roleRef.current = role;
  }, [editorText, scanResult, scanOrigin, role]);

  const showToast = useCallback((msg: string) => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToastMessage(msg);
    toastTimer.current = setTimeout(() => setToastMessage(null), 4000);
  }, []);

  const adopt = useCallback((resp: ScanResponse, origin: Origin) => {
    setScanResult(resp);
    setScanOrigin(origin);
    setSelectedIssueId(resp.issues[0]?.id ?? null);
    setCurrentPage(1);
    if (origin === "live") {
      setKbVersion(resp.kb_version);
      setRulesVersion(resp.rules_version);
      setEngineOnline(true);
      wakingRef.current = false;
      setIsWakingUp(false);
    }
    syncScanIdToUrl(resp.scan_id, resp);
  }, []);

  useEffect(() => {
    const savedRole = localStorage.getItem("cl_role");
    if (savedRole === "Creator" || savedRole === "Reviewer" || savedRole === "Admin") setRole(savedRole);
    const savedWs = localStorage.getItem("cl_workspace");
    if (savedWs === "default" || savedWs === "custom") setWorkspaceId(savedWs);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const ok = await waitForEngine(() => cancelled);
      if (cancelled) return;
      setEngineOnline(ok);
      wakingRef.current = false;
      setIsWakingUp(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const scanId = new URLSearchParams(window.location.search).get("scan_id");
    if (!scanId) return;
    let cancelled = false;

    const applyRestored = (parsed: ScanResponse, origin: Origin) => {
      setScanResult(parsed);
      setScanOrigin(origin);
      if (parsed.redacted_text) {
        setEditorText(parsed.redacted_text);
        setOriginalText(parsed.redacted_text);
      }
      setSelectedIssueId(parsed.issues[0]?.id ?? null);
      if (origin === "live" && (parsed.input_type === "pdf" || parsed.input_type === "image")) {
        setActiveTab("canvas");
      }
    };

    fetchScan(scanId)
      .then((parsed) => {
        if (!cancelled) applyRestored(parsed, "live");
      })
      .catch(() => {
        if (cancelled) return;
        try {
          const cachedRaw = localStorage.getItem("cl_last_scan");
          if (!cachedRaw) return;
          const parsed = ScanResponseSchema.parse(JSON.parse(cachedRaw));
          if (parsed.scan_id === scanId) applyRestored(parsed, "fallback");
        } catch {
          setErrorBanner("Could not restore the saved scan. Run a new audit.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleWorkspaceChange = (next: "default" | "custom") => {
    setWorkspaceId(next);
    localStorage.setItem("cl_workspace", next);
  };

  const handleRoleChange = (next: Role) => {
    setRole(next);
    localStorage.setItem("cl_role", next);
  };

  const handleRunTextAudit = async () => {
    setErrorBanner(null);
    const trimmed = editorText.trim();
    if (trimmed.length < MIN_CHARS) {
      setErrorBanner(`Enter at least ${MIN_CHARS} characters of copy to run an audit.`);
      return;
    }
    if (trimmed.length > MAX_CHARS) {
      setErrorBanner("The draft is over the 8,000 character limit. Shorten it and try again.");
      return;
    }
    if (isScanning) return;

    const id = ++requestId.current;
    setIsScanning(true);
    setScanStep("Auditing copy and verifying claims...");
    try {
      const live = await withColdStartRetry(
        () => runTextScan(trimmed, channel, workspaceId),
        () => setScanStep("Waking the engine, retrying..."),
        () => wakingRef.current
      );
      if (id !== requestId.current) return;
      setOriginalText(trimmed);
      adopt(live, "live");
      showToast("Audit complete.");
    } catch (e) {
      if (id !== requestId.current) return;
      setErrorBanner(`Live audit failed: ${errMsg(e)}. Showing a demo result instead.`);
      setOriginalText(trimmed);
      adopt(buildOfflineTextScan(trimmed), "fallback");
    } finally {
      if (id === requestId.current) {
        setIsScanning(false);
        setScanStep("");
      }
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    setErrorBanner(null);
    const input = e.target;
    const file = input.files?.[0];
    if (!file) return;

    const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
    const isImage = file.type.startsWith("image/");
    if (file.size > MAX_UPLOAD) {
      setErrorBanner("That file is over 5 MB. Choose a smaller file.");
      input.value = "";
      return;
    }
    if (!isPdf && !isImage) {
      setErrorBanner("Unsupported file type. Upload a PDF, PNG, JPG or WebP.");
      input.value = "";
      return;
    }
    if (isScanning) {
      input.value = "";
      return;
    }

    const id = ++requestId.current;
    setIsScanning(true);
    setScanStep(`Scanning ${file.name}...`);
    try {
      const live = await withColdStartRetry(
        () => uploadAssetForScan(isPdf ? "/api/scan-pdf" : "/api/scan-image", file, channel, workspaceId),
        () => setScanStep("Waking the engine, retrying..."),
        () => wakingRef.current
      );
      if (id !== requestId.current) return;
      adopt(live, "live");
      setActiveTab("canvas");
      showToast(`Audit complete for ${file.name}.`);
    } catch (err) {
      if (id !== requestId.current) return;
      setErrorBanner(`Live scan of ${file.name} failed: ${errMsg(err)}. Showing a sample preview instead.`);
      adopt(
        {
          ...MOCK_SCAN_RESPONSE_V3,
          scan_id: `scan_pdf_${Math.random().toString(36).slice(2, 7)}`,
          input_type: isPdf ? "pdf" : "image",
        },
        "fallback"
      );
      setActiveTab("canvas");
    } finally {
      if (id === requestId.current) {
        setIsScanning(false);
        setScanStep("");
      }
      input.value = "";
    }
  };

  const loadSample = useCallback(
    (kind: "violation" | "clean" | "brochure") => {
      setErrorBanner(null);
      if (kind === "clean") {
        setEditorText(SAMPLE_CLEAN_TEXT);
        setOriginalText(SAMPLE_CLEAN_TEXT);
        adopt(MOCK_CLEAN_SCAN_V3, "sample");
        showToast("Loaded the compliant sample.");
      } else if (kind === "violation") {
        setEditorText(SAMPLE_VIOLATION_TEXT);
        setOriginalText(SAMPLE_VIOLATION_TEXT);
        adopt(MOCK_SCAN_RESPONSE_V3, "sample");
        showToast("Loaded the sample with two violations.");
      } else {
        adopt(MOCK_SCAN_RESPONSE_V3, "sample");
        setActiveTab("canvas");
      }
    },
    [adopt, showToast]
  );

  const handleAcceptFix = useCallback(
    (issue: Issue) => {
      const current = scanRef.current;
      if (!current) return;

      const text = editorRef.current;
      const range = resolveRange(text, issue);
      let nextText: string | null = null;
      if (range) {
        nextText = text.slice(0, range.start) + issue.suggested_fix + text.slice(range.end);
      } else if (issue.flagged_text && text.includes(issue.flagged_text)) {
        nextText = text.replaceAll(issue.flagged_text, issue.suggested_fix);
      }
      if (nextText !== null) {
        editorRef.current = nextText; 
        setEditorText(nextText);
      }

      const remaining = current.issues.filter((i) => i.id !== issue.id);
      const updated: ScanResponse = { ...current, readiness_score: calcScore(remaining), issues: remaining };
      scanRef.current = updated;
      setScanResult(updated);
      setSelectedIssueId(remaining[0]?.id ?? null);
      syncScanIdToUrl(updated.scan_id, updated);
      showToast(
        nextText !== null
          ? `Applied fix: ${issue.suggested_fix}`
          : "Marked as resolved. No text change was needed."
      );
    },
    [showToast]
  );

  const handleLocate = useCallback((issue: Issue) => {
    setSelectedIssueId(issue.id);
    setCurrentPage(issue.page ?? 1);
    setActiveTab("canvas");
  }, []);

  const handleUploadClick = useCallback(() => fileInputRef.current?.click(), []);
  const closeCert = useCallback(() => setShowCert(false), []);
  const openCert = useCallback(() => setShowCert(true), []);

  const handleReaudit = () => {
    if (scanRef.current?.input_type === "text") {
      setActiveTab("studio");
      handleRunTextAudit();
    } else {
      showToast("Upload the updated document to re-audit it.");
      fileInputRef.current?.click();
    }
  };

  const handleApprove = useCallback(async () => {
    const current = scanRef.current;
    if (!current) return;

    let sig = { value: DEMO_SIGNATURE, live: false };
    if (originRef.current === "live") {
      const result = await approveScan(current.scan_id, roleRef.current);
      if (!result.signature) {
        setErrorBanner(`Approval failed: ${result.error ?? "unknown error"}. The scan was not signed.`);
        return;
      }
      sig = { value: result.signature, live: true };
    }
    setSignature(sig);
    const approved: ScanResponse = { ...current, status: "approved" };
    setScanResult(approved);
    syncScanIdToUrl(approved.scan_id, approved);
    setShowCert(true);
  }, []);

  const handleSimulatePriceSync = useCallback(() => {
    const nextVer = kbVersion + 1;
    setKbVersion(nextVer);
    setKbChunks((prev) =>
      prev.map((c) =>
        c.chunk_id === 3
          ? {
              ...c,
              fact_text: "The ClaimLoom Pro Plan subscription costs $39/month billed monthly, or $390/year (updated).",
              updated_at: `Synced v${nextVer}`,
            }
          : c
      )
    );
    setAffectedScansCount(2);
    const current = scanRef.current;
    if (current) {
      setScanResult({
        ...current,
        kb_version: nextVer,
        status: "needs_reaudit",
        reaudit: {
          needed: true,
          note: `Pricing fact in Approved_Pricing_Policy.md changed to $39/mo (KB v${nextVer}).`,
        },
      });
    }
    showToast(`Truth Vault synced to v${nextVer}. 2 approved drafts need a re-audit.`);
  }, [kbVersion, showToast]);

  const handleAddRule = useCallback(
    (name: string, pattern: string) => {
      setRules((prev) => [
        ...prev,
        { id: Math.max(0, ...prev.map((r) => r.id)) + 1, name, category: "Custom", severity: "High", pattern },
      ]);
      setRulesVersion((v) => v + 1);
      showToast("Rule added.");
    },
    [showToast]
  );

  const handleOptimizeRule = useCallback(() => {
    setRuleOptimized(true);
    setRulesVersion((v) => v + 1);
    showToast("Rule #3 rewritten, backtested and committed.");
  }, [showToast]);

  const handleResetDemo = () => {
    requestId.current++;
    setIsScanning(false);
    setScanStep("");
    setKbVersion(1);
    setRulesVersion(1);
    setKbChunks(INITIAL_KB_CHUNKS);
    setAffectedScansCount(0);
    setRuleOptimized(false);
    setRules(INITIAL_RULES);
    setEditorText("");
    setOriginalText("");
    setScanResult(null);
    setSelectedIssueId(null);
    setCurrentPage(1);
    setShowCert(false);
    setErrorBanner(null);
    localStorage.removeItem("cl_last_scan");
    window.history.replaceState({}, "", window.location.pathname);
    showToast("Workspace reset.");
  };

  const issues = scanResult?.issues ?? [];
  const highCount = issues.filter((i) => i.severity === "High").length;
  const isApproved = scanResult?.status === "approved";
  const canApprove =
    Boolean(scanResult) && role !== "Creator" && highCount === 0 && !scanResult?.reaudit?.needed && !isApproved;
  const isLive = engineOnline && scanOrigin !== "fallback";

  let signoffHint = "Run an audit to enable approval.";
  if (scanResult) {
    if (isApproved) signoffHint = "Approved and signed.";
    else if (scanResult.reaudit?.needed) signoffHint = "A knowledge update requires a re-audit first.";
    else if (highCount > 0)
      signoffHint = `Resolve ${highCount} high-severity ${highCount === 1 ? "issue" : "issues"} to unlock approval.`;
    else if (role === "Creator") signoffHint = "No blockers left. Switch to Reviewer or Admin to sign off.";
    else signoffHint = "Ready to sign. This creates a tamper-evident certificate.";
  }

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900">
      <div className="print:hidden">
        {isWakingUp && (
          <div role="status" className="bg-amber-50 px-6 py-1.5 text-center text-xs font-medium text-amber-900">
            Waking the audit engine. Free hosting can take up to a minute, and you can keep working.
          </div>
        )}
        {scanResult?.reaudit?.needed && (
          <div className="flex flex-wrap items-center justify-between gap-2 bg-red-600 px-6 py-2 text-xs font-medium text-white">
            <span>Re-audit required: {scanResult.reaudit.note}</span>
            <button
              type="button"
              onClick={handleReaudit}
              className="rounded bg-white px-2.5 py-1 font-semibold text-red-700 hover:bg-red-50"
            >
              Re-audit now
            </button>
          </div>
        )}
      </div>

      {toastMessage && (
        <div
          role="status"
          className="fixed bottom-5 right-5 z-50 flex max-w-sm items-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-xs text-white shadow-lg print:hidden"
        >
          <span className="h-2 w-2 shrink-0 rounded-full bg-emerald-400" />
          <span>{toastMessage}</span>
        </div>
      )}

      <header className="border-b border-slate-200 bg-white print:hidden">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 text-sm font-bold text-white">
              CL
            </div>
            <div>
              <h1 className="text-base font-bold leading-tight tracking-tight">ClaimLoom</h1>
              <p className="text-xs text-slate-500">Brand governance and claim verification</p>
            </div>
            <span
              className={`ml-2 inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${
                isLive ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-800"
              }`}
            >
              <span className={`h-1.5 w-1.5 rounded-full ${isLive ? "bg-emerald-500" : "bg-amber-500"}`} />
              {isLive ? "Live engine" : "Demo mode"}
              <span className="font-normal text-slate-500">
                KB v{kbVersion}, Rules v{rulesVersion}
              </span>
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-4 text-xs text-slate-600">
            <label className="flex items-center gap-2">
              Brand
              <select
                value={workspaceId}
                onChange={(e) => handleWorkspaceChange(e.target.value as "default" | "custom")}
                className={selectCls}
              >
                <option value="default">ClaimLoom (default)</option>
                <option value="custom">My custom brand (sandbox)</option>
              </select>
            </label>
            <label className="flex items-center gap-2">
              Persona
              <select value={role} onChange={(e) => handleRoleChange(e.target.value as Role)} className={selectCls}>
                <option value="Creator">Creator: draft and fix</option>
                <option value="Reviewer">Reviewer: approve and sign</option>
                <option value="Admin">Admin: rules and radar</option>
              </select>
            </label>
            <button type="button" onClick={handleResetDemo} className={btnGhost}>
              Reset
            </button>
          </div>
        </div>

        <div className="mx-auto max-w-7xl overflow-x-auto px-6">
          <nav role="tablist" aria-label="Workspace" className="flex min-w-max gap-6">
            {TABS.map((t) => {
              const active = activeTab === t.id;
              const badge = t.id === "studio" ? (issues.length > 0 ? String(issues.length) : null) : t.id === "vault" ? `v${kbVersion}` : null;
              return (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => setActiveTab(t.id)}
                  className={`flex items-center gap-2 border-b-2 py-3 text-sm font-semibold transition-colors ${
                    active ? "border-blue-600 text-blue-700" : "border-transparent text-slate-500 hover:text-slate-900"
                  }`}
                >
                  {t.label}
                  {badge && (
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs ${
                        active ? "bg-blue-50 text-blue-700" : "bg-slate-100 text-slate-600"
                      }`}
                    >
                      {badge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>
      </header>

      {errorBanner && (
        <div
          role="alert"
          className="mx-auto mt-4 flex w-full max-w-7xl items-start justify-between gap-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 print:hidden"
        >
          <span>{errorBanner}</span>
          <button type="button" onClick={() => setErrorBanner(null)} className="shrink-0 font-semibold hover:underline">
            Dismiss
          </button>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.png,.jpg,.jpeg,.webp"
        onChange={handleFileUpload}
        className="hidden"
      />

      <main className="mx-auto w-full max-w-7xl flex-1 px-6 py-6 print:hidden">
        <div className={activeTab === "studio" ? "block" : "hidden"}>
          <div className="grid items-start gap-6 lg:grid-cols-12">
            <div className="space-y-6 lg:col-span-7">
              <EditorCard
                text={editorText}
                onTextChange={setEditorText}
                original={originalText}
                channel={channel}
                onChannelChange={setChannel}
                isScanning={isScanning}
                scanStep={scanStep}
                onRun={handleRunTextAudit}
                onUploadClick={handleUploadClick}
                onSample={loadSample}
                issues={issues}
                selectedIssueId={selectedIssueId}
                onSelectIssue={setSelectedIssueId}
              />
              <SignoffCard
                role={role}
                hint={signoffHint}
                canApprove={canApprove}
                isApproved={isApproved}
                onApprove={handleApprove}
                onViewCertificate={openCert}
              />
            </div>
            <div className="lg:col-span-5">
              <ResultsPanel
                scanResult={scanResult}
                isScanning={isScanning}
                origin={scanOrigin}
                selectedIssueId={selectedIssueId}
                onSelect={setSelectedIssueId}
                onLocate={handleLocate}
                onAccept={handleAcceptFix}
                onSample={loadSample}
              />
            </div>
          </div>
        </div>

        <div className={activeTab === "canvas" ? "block" : "hidden"}>
          <CanvasTab
            scanResult={scanResult}
            origin={scanOrigin}
            currentPage={currentPage}
            onPageChange={setCurrentPage}
            selectedIssueId={selectedIssueId}
            onSelectIssue={setSelectedIssueId}
            onResolve={handleAcceptFix}
            onUploadClick={handleUploadClick}
            onSample={loadSample}
          />
        </div>

        <div className={activeTab === "vault" ? "block" : "hidden"}>
          <VaultTab
            kbVersion={kbVersion}
            chunks={kbChunks}
            affectedCount={affectedScansCount}
            onSync={handleSimulatePriceSync}
            rules={rules}
            onAddRule={handleAddRule}
          />
        </div>

        <div className={activeTab === "radar" ? "block" : "hidden"}>
          <RadarTab ruleOptimized={ruleOptimized} onOptimize={handleOptimizeRule} />
        </div>
      </main>

      {showCert && scanResult && (
        <CertificateModal scan={scanResult} role={role} signature={signature} onClose={closeCert} />
      )}
    </div>
  );
}