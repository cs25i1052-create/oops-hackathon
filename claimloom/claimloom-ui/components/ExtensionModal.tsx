"use client";

import React, { useEffect, useState } from "react";
import { API_BASE, runTextScan } from "../lib/api";
import type { ScanResponse, Issue } from "../lib/schema";
import { btnGhost, btnPrimary, selectCls } from "../lib/ui";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  defaultChannel: string;
  defaultWorkspace: string;
}

const SAMPLE_COPY =
  "The ClaimLoom Pro Plan costs $15/month and gives a 100% guarantee with zero errors on all claims.";

export default function ExtensionModal({
  isOpen,
  onClose,
  defaultChannel,
  defaultWorkspace,
}: Props) {
  const [activeTab, setActiveTab] = useState<"install" | "simulator">("install");
  const [copiedUrl, setCopiedUrl] = useState(false);

  // Simulator State
  const [simWorkspace, setSimWorkspace] = useState(defaultWorkspace || "default");
  const [simChannel, setSimChannel] = useState(defaultChannel || "general");
  const [simText, setSimText] = useState(SAMPLE_COPY);
  const [isScanning, setIsScanning] = useState(false);
  const [scanResult, setScanResult] = useState<ScanResponse | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const [copiedFixId, setCopiedFixId] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (isOpen) {
      setSimWorkspace(defaultWorkspace || "default");
      setSimChannel(defaultChannel || "general");
    }
  }, [isOpen, defaultWorkspace, defaultChannel]);

  if (!isOpen) return null;

  const handleCopyExtensionsUrl = async () => {
    try {
      await navigator.clipboard.writeText("chrome://extensions");
      setCopiedUrl(true);
      setTimeout(() => setCopiedUrl(false), 2000);
    } catch {
      setCopiedUrl(false);
    }
  };

  const handleSimScan = async () => {
    if (!simText.trim()) {
      setScanError("Please enter some text to scan.");
      return;
    }
    setIsScanning(true);
    setScanError(null);
    try {
      const res = await runTextScan(simText.trim(), simChannel, simWorkspace);
      setScanResult(res);
    } catch (err) {
      setScanError(err instanceof Error ? err.message : "Scan failed.");
    } finally {
      setIsScanning(false);
    }
  };

  const handleCopyFix = async (fix: string, issueKey: string) => {
    if (!fix) return;
    try {
      await navigator.clipboard.writeText(fix);
      setCopiedFixId(issueKey);
      setTimeout(() => setCopiedFixId(null), 1500);
    } catch {
      // ignore
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="ClaimLoom Chrome Extension"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl max-h-[90vh] flex flex-col rounded-xl border border-slate-200 bg-white shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-xs font-bold text-white">
              CL
            </div>
            <div>
              <h2 className="text-sm font-bold text-slate-900">ClaimLoom Chrome Extension</h2>
              <p className="text-xs text-slate-500">Real-time copy governance in your browser</p>
            </div>
          </div>
          <button
            type="button"
            aria-label="Close modal"
            onClick={onClose}
            className="text-xs font-semibold text-slate-500 hover:text-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 rounded px-2 py-1"
          >
            Close
          </button>
        </div>

        {/* Tab Switcher */}
        <div className="border-b border-slate-200 bg-slate-50 px-6">
          <nav className="flex gap-4" aria-label="Extension tabs">
            <button
              type="button"
              onClick={() => setActiveTab("install")}
              className={`border-b-2 py-3 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 ${
                activeTab === "install"
                  ? "border-blue-600 text-blue-700"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              📦 Install in Chrome (Manifest V3)
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("simulator")}
              className={`border-b-2 py-3 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 ${
                activeTab === "simulator"
                  ? "border-blue-600 text-blue-700"
                  : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              ⚡ Try Live Popup Simulator (No Install)
            </button>
          </nav>
        </div>

        {/* Tab Body */}
        <div className="p-6 overflow-y-auto flex-1">
          {activeTab === "install" && (
            <div className="space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 rounded-xl border border-blue-100 bg-blue-50/70 p-4">
                <div>
                  <h3 className="text-sm font-semibold text-blue-950">Download Extension Bundle</h3>
                  <p className="text-xs text-blue-800 mt-0.5">
                    Includes Manifest V3, workspace switcher, and one-click copy checking.
                  </p>
                </div>
                <a
                  href={`${API_BASE}/api/extension/download`}
                  download="ClaimLoom-Chrome-Extension.zip"
                  className={btnPrimary}
                >
                  ⬇️ Download Extension (.zip)
                </a>
              </div>

              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3">
                  3-Step Installation Guide (Chrome / Edge / Brave)
                </h4>
                <ol className="space-y-3 text-xs text-slate-700">
                  <li className="flex items-start gap-3 rounded-lg border border-slate-200 bg-white p-3.5 shadow-sm">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-600 font-bold text-white text-[11px]">
                      1
                    </span>
                    <div>
                      <strong className="text-slate-900 block mb-0.5">Download & Unzip</strong>
                      Download <code className="rounded bg-slate-100 px-1 py-0.5">ClaimLoom-Chrome-Extension.zip</code> and extract the files to a folder on your computer.
                    </div>
                  </li>

                  <li className="flex items-start gap-3 rounded-lg border border-slate-200 bg-white p-3.5 shadow-sm">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-600 font-bold text-white text-[11px]">
                      2
                    </span>
                    <div className="space-y-2 flex-1">
                      <div>
                        <strong className="text-slate-900 block mb-0.5">Open Extensions Settings</strong>
                        Navigate to <code className="rounded bg-slate-100 px-1 py-0.5 font-mono">chrome://extensions</code> in your address bar and turn on <strong>Developer mode</strong> in the top-right corner.
                      </div>
                      <div>
                        <button
                          type="button"
                          onClick={handleCopyExtensionsUrl}
                          className={btnGhost}
                        >
                          {copiedUrl ? "✅ Copied!" : "📋 Copy chrome://extensions"}
                        </button>
                      </div>
                    </div>
                  </li>

                  <li className="flex items-start gap-3 rounded-lg border border-slate-200 bg-white p-3.5 shadow-sm">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-600 font-bold text-white text-[11px]">
                      3
                    </span>
                    <div>
                      <strong className="text-slate-900 block mb-0.5">Load Unpacked</strong>
                      Click the <strong>Load unpacked</strong> button in the top left and select your extracted extension folder. ClaimLoom will appear in your browser toolbar!
                    </div>
                  </li>
                </ol>
              </div>

              <div className="rounded-lg bg-slate-50 p-3 text-[11px] text-slate-600 border border-slate-200">
                💡 <strong>Tip:</strong> Pin the ClaimLoom extension to your browser toolbar. When composing copy on LinkedIn, CMS editors, or Google Docs, select text on the page and open ClaimLoom to audit compliance instantly.
              </div>
            </div>
          )}

          {activeTab === "simulator" && (
            <div className="space-y-4">
              <p className="text-xs text-slate-500 text-center">
                Interactive 360px popup replica running live against the ClaimLoom backend.
              </p>

              {/* 360px Mini Replica */}
              <div className="mx-auto w-[360px] max-w-full rounded-2xl border border-slate-300 bg-white p-4 shadow-xl text-slate-800">
                {/* Simulator Header */}
                <header className="flex items-center gap-3 border-b border-slate-100 pb-3 mb-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#1e3a8a] text-sm font-extrabold text-white">
                    CL
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-slate-900 leading-tight">ClaimLoom</h4>
                    <p className="text-[11px] text-slate-500">Pre-publication copy check</p>
                  </div>
                </header>

                <div className="space-y-3 text-xs">
                  {/* Workspace Dropdown */}
                  <div>
                    <label htmlFor="sim-workspace" className="block font-semibold text-slate-700 mb-1">
                      Workspace
                    </label>
                    <select
                      id="sim-workspace"
                      value={simWorkspace}
                      onChange={(e) => setSimWorkspace(e.target.value)}
                      className="w-full rounded-lg border border-slate-300 bg-white p-2 text-xs font-medium focus:border-blue-600 focus:outline-none"
                    >
                      <option value="default">ClaimLoom Official</option>
                      <option value="custom_brand">My Custom Brand Sandbox</option>
                    </select>
                  </div>

                  {/* Channel Dropdown */}
                  <div>
                    <label htmlFor="sim-channel" className="block font-semibold text-slate-700 mb-1">
                      Channel
                    </label>
                    <select
                      id="sim-channel"
                      value={simChannel}
                      onChange={(e) => setSimChannel(e.target.value)}
                      className="w-full rounded-lg border border-slate-300 bg-white p-2 text-xs font-medium focus:border-blue-600 focus:outline-none"
                    >
                      <option value="general">General</option>
                      <option value="linkedin">LinkedIn</option>
                      <option value="instagram">Instagram</option>
                      <option value="billboard">Billboard</option>
                      <option value="email">Email</option>
                    </select>
                  </div>

                  {/* Text Input */}
                  <div>
                    <label htmlFor="sim-text" className="block font-semibold text-slate-700 mb-1">
                      Text to scan (select text or paste here)
                    </label>
                    <textarea
                      id="sim-text"
                      rows={4}
                      value={simText}
                      onChange={(e) => setSimText(e.target.value)}
                      placeholder="Paste copy here to audit against Brand Truth Vault..."
                      className="w-full resize-y rounded-lg border border-slate-300 bg-white p-2 text-xs focus:border-blue-600 focus:outline-none"
                    />
                  </div>

                  {/* Scan Button */}
                  <button
                    type="button"
                    disabled={isScanning}
                    onClick={handleSimScan}
                    className="w-full rounded-lg bg-[#1e3a8a] py-2.5 text-xs font-bold text-white hover:bg-blue-800 disabled:opacity-60 disabled:cursor-wait transition"
                  >
                    {isScanning ? "Scanning copy…" : "Scan copy"}
                  </button>

                  {/* Status */}
                  {scanError && (
                    <p className="text-[11px] text-red-600 font-medium">{scanError}</p>
                  )}
                  {!scanResult && !scanError && (
                    <p className="text-[11px] text-slate-500">Ready to audit copy against brand rules.</p>
                  )}

                  {/* Results Display */}
                  {scanResult && (
                    <div className="pt-2 border-t border-slate-100 space-y-3">
                      <div className="flex items-center justify-between font-bold text-xs">
                        <span>Readiness: {scanResult.readiness_score}/100</span>
                        <span className="capitalize text-slate-600 font-medium">{scanResult.status}</span>
                      </div>

                      {/* Pillar Scores */}
                      {scanResult.pillar_scores && (
                        <div className="grid grid-cols-2 gap-1.5">
                          {Object.entries(scanResult.pillar_scores).map(([name, score]) => (
                            <div
                              key={name}
                              className="rounded bg-slate-100 px-2 py-1 text-[11px] text-slate-700 font-medium"
                            >
                              {name}: {score}/100
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Issue Cards */}
                      <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
                        {scanResult.issues.length === 0 ? (
                          <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-2 text-[11px] text-emerald-800 font-medium text-center">
                            ✅ No issues found in the copy.
                          </div>
                        ) : (
                          scanResult.issues.map((issue: Issue, idx: number) => {
                            const issueKey = `${issue.rule_id}-${idx}`;
                            return (
                              <article
                                key={issueKey}
                                className="rounded-lg border border-red-200 bg-white p-2.5 shadow-sm space-y-1.5"
                              >
                                <strong className="block text-[11px] font-bold text-red-800">
                                  {issue.severity || "Issue"} · {issue.violation_type || "Governance"}
                                </strong>
                                <p className="text-[11px] text-slate-600 break-words leading-relaxed">
                                  <span className="text-red-700 font-medium">{issue.flagged_text || "Flagged text"}</span>
                                  {" → "}
                                  <span className="text-emerald-700 font-medium">{issue.suggested_fix || "No fix"}</span>
                                </p>
                                {issue.suggested_fix && (
                                  <button
                                    type="button"
                                    onClick={() => handleCopyFix(issue.suggested_fix!, issueKey)}
                                    className="w-full rounded bg-slate-100 hover:bg-slate-200 py-1 text-[11px] font-semibold text-slate-800 transition"
                                  >
                                    {copiedFixId === issueKey ? "✅ Copied Fix" : "Copy Suggested Fix"}
                                  </button>
                                )}
                              </article>
                            );
                          })
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
