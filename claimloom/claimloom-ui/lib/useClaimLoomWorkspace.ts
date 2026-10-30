"use client";
import React, { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE, getAuthHeaders, runTextScan, uploadAssetForScan, syncScanIdToUrl, ensureSessionToken } from "./api";
import { approveScan, fetchScan, waitForEngine, withColdStartRetry } from "./client";
import { MOCK_SCAN_RESPONSE_V3, MOCK_CLEAN_SCAN_V3 } from "./mockData";
import { VIOLATION_SAMPLE, CLEAN_SAMPLE } from "./presets";
import type { KBChunkItem } from "./mockData";
import { ScanResponse, ScanResponseSchema, Issue } from "./schema";
import { BrandRule, Origin, Role, Tab, calcScore, errMsg, resolveRange } from "./ui";
import { MAX_CHARS } from "../components/EditorCard";

const MAX_UPLOAD = 5 * 1024 * 1024;
const MIN_CHARS = 10;
const EMPTY_ISSUES: Issue[] = [];
const TABS: { id: Tab; label: string }[] = [
  { id: "studio", label: "Studio" },
  { id: "canvas", label: "Canvas" },
  { id: "vault", label: "Truth Vault" },
  { id: "radar", label: "Governance Radar" },
];
function buildOfflineTextScan(text: string): ScanResponse {
  const lower = text.toLowerCase();
  const base = lower.includes("$15/month") || lower.includes("guaranteed 100%") ? MOCK_SCAN_RESPONSE_V3 : MOCK_CLEAN_SCAN_V3;
  const issues = base.issues.filter((i) => i.flagged_text && lower.includes(i.flagged_text.toLowerCase()));
  return { ...base, scan_id: `scan_${Math.random().toString(36).slice(2, 8)}`, input_type: "text", redacted_text: text, issues, readiness_score: issues.length === base.issues.length ? base.readiness_score : calcScore(issues) };
}
function isNetworkFailure(error: unknown): boolean {
  return error instanceof TypeError || (error instanceof Error && error.name === "AbortError");
}
export function useClaimLoomWorkspace() {

  const [activeTab, setActiveTab] = useState<Tab>("studio");
  const [role, setRole] = useState<Role>(() => {
    if (typeof window === "undefined") return "Reviewer";
    const saved = localStorage.getItem("cl_role");
    return saved === "Creator" || saved === "Admin" ? saved : "Reviewer";
  });
  const [workspaceId, setWorkspaceId] = useState<"default" | "custom_brand">(() => {
    if (typeof window === "undefined") return "default";
    return localStorage.getItem("cl_workspace") === "custom_brand" || localStorage.getItem("cl_workspace") === "custom" ? "custom_brand" : "default";
  });
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
  const [signature, setSignature] = useState<{ value: string; live: boolean; entry_hash?: string; text_sha256?: string; prev_hash?: string; reviewer?: string }>({
    value: "",
    live: false,
  });
  const [certificatePublicKey, setCertificatePublicKey] = useState<string | null>(null);

  const [kbChunks, setKbChunks] = useState<KBChunkItem[]>([]);
  const [affectedScansCount, setAffectedScansCount] = useState(0);
  const [rules, setRules] = useState<BrandRule[]>([]);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestId = useRef(0);
  const wakingRef = useRef(true);
  const editorRef = useRef("");
  const editorOriginalRef = useRef("");
  const scanRef = useRef<ScanResponse | null>(null);
  const originRef = useRef<Origin>("sample");
  const roleRef = useRef<Role>("Reviewer");
  const workspaceRef = useRef(workspaceId);

  useEffect(() => {
    editorRef.current = editorText;
    editorOriginalRef.current = originalText;
    scanRef.current = scanResult;
    originRef.current = scanOrigin;
    roleRef.current = role;
    workspaceRef.current = workspaceId;
  }, [editorText, originalText, scanResult, scanOrigin, role, workspaceId]);

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
    void ensureSessionToken(roleRef.current, localStorage.getItem("cl_name") || "Judge Reviewer", workspaceRef.current).catch((e) => setErrorBanner(e.message));
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

  // Patch 1: Fast restore with single cold-start retry
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

    withColdStartRetry(
      () => fetchScan(scanId),
      undefined,
      () => wakingRef.current
    )
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

  const handleWorkspaceChange = async (next: "default" | "custom_brand") => {
    try {
      await ensureSessionToken(roleRef.current, localStorage.getItem("cl_name") || "Judge Reviewer", next);
      setWorkspaceId(next);
      localStorage.setItem("cl_workspace", next);
      setEngineOnline(true);
      setScanResult(null);
      setScanOrigin("sample");
      setSelectedIssueId(null);
      localStorage.removeItem("cl_last_scan");
      const url = new URL(window.location.href);
      url.searchParams.delete("scan_id");
      window.history.replaceState({}, "", url.toString());
    } catch (e) { setEngineOnline(false); setErrorBanner(errMsg(e)); }
  };

  const handleRoleChange = async (next: Role) => {
    roleRef.current = next;
    setRole(next);
    localStorage.setItem("cl_role", next);
    try {
      await ensureSessionToken(next, localStorage.getItem("cl_name") || "Judge Reviewer", workspaceRef.current);
      setErrorBanner(null);
    } catch (e) {
      setErrorBanner(errMsg(e));
    }
  };

  const handleRunTextAudit = async () => {
    if (isScanning) return;
    setErrorBanner(null);

    if (editorText.trim().length < MIN_CHARS) {
      setErrorBanner(`Enter at least ${MIN_CHARS} characters of copy to run an audit.`);
      return;
    }
    if (editorText.trim().length > MAX_CHARS) {
      setErrorBanner(`The draft is over the ${MAX_CHARS.toLocaleString()} character limit.`);
      return;
    }

    const id = ++requestId.current;
    setIsScanning(true);
    setScanStep("Auditing copy and verifying claims...");
    try {
      const live = await withColdStartRetry(
        () => runTextScan(editorText, channel, workspaceId),
        () => setScanStep("Waking the engine, retrying..."),
        () => wakingRef.current
      );
      if (id !== requestId.current) return;
      setOriginalText(editorText);
      adopt(live, "live");
      showToast("Audit complete.");
    } catch (e) {
      if (id !== requestId.current) return;
      if (isNetworkFailure(e)) {
        setEngineOnline(false);
        setErrorBanner(`Backend connection failed: ${errMsg(e)}. Showing the read-only offline demo.`);
        setOriginalText(editorText);
        adopt(buildOfflineTextScan(editorText), "fallback");
      } else {
        setErrorBanner(`Live audit failed: ${errMsg(e)}`);
      }
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
      if (isNetworkFailure(err)) {
        setEngineOnline(false);
        setErrorBanner(`Backend connection failed: ${errMsg(err)}. Offline previews are read-only.`);
        adopt({ ...MOCK_SCAN_RESPONSE_V3, scan_id: `scan_pdf_${Math.random().toString(36).slice(2, 7)}`, input_type: isPdf ? "pdf" : "image" }, "fallback");
        setActiveTab("canvas");
      } else setErrorBanner(`Live scan of ${file.name} failed: ${errMsg(err)}`);
    } finally {
      if (id === requestId.current) {
        setIsScanning(false);
        setScanStep("");
      }
      input.value = "";
    }
  };

  const loadSample = useCallback(
    async (kind: "violation" | "clean" | "brochure") => {
      setErrorBanner(null);
      if (kind === "clean") {
        setEditorText(CLEAN_SAMPLE);
        setOriginalText(CLEAN_SAMPLE);
        if (engineOnline) { setScanResult(null); setScanOrigin("sample"); }
        else adopt(MOCK_CLEAN_SCAN_V3, "sample");
        showToast(engineOnline ? "Sample copy loaded. Run an audit for live results." : "Loaded the read-only compliant sample.");
      } else if (kind === "violation") {
        setEditorText(VIOLATION_SAMPLE);
        setOriginalText(VIOLATION_SAMPLE);
        if (engineOnline) { setScanResult(null); setScanOrigin("sample"); }
        else adopt(MOCK_SCAN_RESPONSE_V3, "sample");
        showToast(engineOnline ? "Sample copy loaded. Run an audit for live results." : "Loaded the read-only violation sample.");
      } else {
        if (!engineOnline) {
          adopt(MOCK_SCAN_RESPONSE_V3, "sample");
          setActiveTab("canvas");
          return;
        }
        try {
          const form = new FormData();
          form.append("channel", channel);
          form.append("workspace_id", workspaceId);
          const response = await fetch(`${API_BASE}/api/scan-sample-pdf`, {
            method: "POST",
            headers: getAuthHeaders(),
            body: form,
          });
          const data = await response.json().catch(() => null) as { detail?: string } | null;
          if (!response.ok) throw new Error(data?.detail || `Sample brochure scan failed (HTTP ${response.status}).`);
          const live = ScanResponseSchema.parse(data);
          const text = live.redacted_text || "";
          setEditorText(text);
          setOriginalText(text);
          adopt(live, "live");
          setActiveTab("canvas");
          showToast("Sample brochure scanned. Review its live page findings and bounding boxes.");
        } catch (e) {
          setErrorBanner(errMsg(e));
        }
      }
    },
    [adopt, channel, engineOnline, setEditorText, setErrorBanner, setOriginalText, setScanResult, setScanOrigin, setActiveTab, showToast, workspaceId]
  );

  // Patch 3: Track pending fixes on live scans so sign-off requires re-audit
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

  const handleActivityReaudit = useCallback((needed: boolean, note?: string | null) => {
    setScanResult((current) => current ? { ...current, status: needed ? "needs_reaudit" : current.status, reaudit: { needed, note: note || null } } : current);
  }, []);

  const handleApprove = useCallback(async () => {
    const current = scanRef.current;
    if (!current) return;
    const approvingRole = roleRef.current;
    if (approvingRole !== "Reviewer" && approvingRole !== "Admin") {
      setErrorBanner("Switch to Reviewer or Admin before approving this scan.");
      return;
    }
    if (originRef.current !== "live") {
      setErrorBanner("Run a live audit before signing. Offline sample scans are read-only.");
      return;
    }

    let sig = { value: "", live: false };
    try {
      await ensureSessionToken(approvingRole, localStorage.getItem("cl_name") || "Judge Reviewer", workspaceRef.current);
      const snapshot = editorRef.current !== editorOriginalRef.current ? editorRef.current : undefined;
      const result = await approveScan(current.scan_id, approvingRole, snapshot);
      if (!result.approval?.signature) {
        setErrorBanner(`Approval failed: ${result.error ?? "unknown error"}. The scan was not signed.`);
        return;
      }
      sig = { value: result.approval.signature, live: true };
      Object.assign(sig, { entry_hash: result.approval.entry_hash, text_sha256: result.approval.text_sha256, prev_hash: result.approval.prev_hash, reviewer: result.approval.reviewer });
      setCertificatePublicKey(result.public_key);
    } catch (e) {
      setErrorBanner(`Approval failed: ${errMsg(e)}. The scan was not signed.`);
      return;
    }
    setSignature(sig);
    const approved: ScanResponse = { ...current, status: "approved" };
    setScanResult(approved);
    syncScanIdToUrl(approved.scan_id, approved);
    setShowCert(true);
  }, []);

  const handleSimulatePriceSync = useCallback(async () => {
    const updatedFact = "ClaimLoom Pro Plan subscription price is $39/month or $390/year.";
    try {
      const response = await fetch(`${API_BASE}/api/kb/chunks/3`, {
        method: "PUT", headers: getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ chunk_text: updatedFact }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Knowledge sync failed");
      setKbVersion(data.kb_version);
      setAffectedScansCount(data.affected_count || 0);
      setKbChunks((current) => {
        const exists = current.some((item) => item.chunk_id === 3);
        const updated = current.map((item) => item.chunk_id === 3
          ? { ...item, fact_text: updatedFact, updated_at: new Date().toISOString() }
          : item);
        return exists ? updated : [...updated, {
          chunk_id: 3,
          doc_title: "Approved Pricing Sheet Q4",
          page: 1,
          category: "Pricing",
          fact_text: updatedFact,
          updated_at: new Date().toISOString(),
        }];
      });
      const current = scanRef.current;
      if (current && (data.affected_scans || []).includes(current.scan_id)) {
        const fresh = await fetchScan(current.scan_id);
        setScanResult(fresh);
      }
      showToast(`Truth Vault updated. ${data.affected_count || 0} scans need re-audit.`);
    } catch (e) { setErrorBanner(e instanceof Error ? e.message : "Knowledge sync failed"); }
  }, [showToast, setKbChunks]);

  const handleResetDemo = () => {
    requestId.current++;
    setIsScanning(false);
    setScanStep("");
    setKbVersion(1);
    setRulesVersion(1);
    setKbChunks([]);
    setAffectedScansCount(0);
    setRules([]);
    setEditorText("");
    setOriginalText("");
    setScanResult(null);
    setSelectedIssueId(null);
    setCurrentPage(1);
    setShowCert(false);
    setErrorBanner(null);
    localStorage.removeItem("cl_last_scan");
    window.history.replaceState({}, "", window.location.pathname);
    showToast("Resetting workspace data…");
    void fetch(`${API_BASE}/api/admin/reset-demo`, { method: "POST", headers: getAuthHeaders() })
      .then(async (response) => {
        const data = await response.json().catch(() => null) as { detail?: string } | null;
        if (!response.ok) throw new Error(data?.detail || `Workspace reset failed (HTTP ${response.status}).`);
        showToast("Workspace reset.");
      })
      .catch((e: unknown) => setErrorBanner(errMsg(e)));
  };

  const issues = scanResult?.issues ?? EMPTY_ISSUES;
  const blockerCount = issues.filter((i) => i.severity === "High" || i.severity === "Medium").length;
  const isApproved = scanResult?.status === "approved";
  const canApprove =
    Boolean(scanResult) &&
    (role === "Reviewer" || role === "Admin") &&
    scanOrigin === "live" &&
    (scanResult?.readiness_score ?? 0) >= 90 &&
    blockerCount === 0 &&
    !scanResult?.reaudit?.needed &&
    !isApproved;
  const isLive = engineOnline;

  let signoffHint = "Run an audit to enable approval.";
  if (scanResult) {
    if (isApproved) signoffHint = "Approved and signed.";
    else if (scanResult.reaudit?.needed) signoffHint = "A knowledge update requires a re-audit first.";
    else if (blockerCount > 0)
      signoffHint = `Resolve ${blockerCount} High or Medium ${blockerCount === 1 ? "issue" : "issues"} to unlock approval.`;
    else if ((scanResult.readiness_score ?? 0) < 90)
      signoffHint = "Readiness must be at least 90 to unlock approval.";
    else if (role === "Creator") signoffHint = "No blockers left. Switch to Reviewer or Admin to sign off.";
    else signoffHint = "Ready to sign. This creates a tamper-evident certificate.";
  }

  return { TABS, activeTab, setActiveTab, role, workspaceId, channel, setChannel, engineOnline, isLive, isWakingUp, kbVersion, rulesVersion, editorText, setEditorText, originalText, isScanning, scanStep, scanResult, setScanResult, scanOrigin, selectedIssueId, setSelectedIssueId, currentPage, setCurrentPage, errorBanner, setErrorBanner, toastMessage, showCert, signature, certificatePublicKey, kbChunks, affectedScansCount, rules, fileInputRef, issues, canApprove, isApproved, signoffHint, handleReaudit, handleWorkspaceChange, handleRoleChange, handleResetDemo, handleFileUpload, handleRunTextAudit, handleUploadClick, loadSample, handleApprove, openCert, closeCert, handleActivityReaudit, handleLocate, handleAcceptFix, handleSimulatePriceSync, showToast, setRules, setKbChunks, setRulesVersion, setKbVersion, setAffectedScansCount, scanRef, fetchScan };
}
