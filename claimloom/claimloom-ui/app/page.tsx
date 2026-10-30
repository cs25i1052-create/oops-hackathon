"use client";

import { useState } from "react";
import { useClaimLoomWorkspace } from "../lib/useClaimLoomWorkspace";

import EditorCard from "../components/EditorCard";
import SignoffCard from "../components/SignoffCard";
import ResultsPanel from "../components/ResultsPanel";
import CanvasTab from "../components/CanvasTab";
import VaultTab from "../components/VaultTab";
import RadarTab from "../components/RadarTab";
import CertificateModal from "../components/CertificateModal";
import ExtensionModal from "../components/ExtensionModal";

import { Role, Tab, btnGhost, selectCls } from "../lib/ui";

export default function ClaimLoomWorkspace() {
  const [showExtensionModal, setShowExtensionModal] = useState(false);
  const { TABS, activeTab, setActiveTab, role, workspaceId, channel, setChannel, isLive, isWakingUp, kbVersion, rulesVersion, editorText, setEditorText, originalText, isScanning, scanStep, scanResult, setScanResult, scanOrigin, selectedIssueId, setSelectedIssueId, currentPage, setCurrentPage, errorBanner, setErrorBanner, toastMessage, showCert, signature, certificatePublicKey, kbChunks, affectedScansCount, rules, fileInputRef, issues, canApprove, isApproved, signoffHint, handleReaudit, handleWorkspaceChange, handleRoleChange, handleResetDemo, handleFileUpload, handleRunTextAudit, handleUploadClick, loadSample, handleApprove, openCert, closeCert, handleActivityReaudit, handleLocate, handleAcceptFix, handleOverride, handleSimulatePriceSync, setRules, setKbChunks, setRulesVersion, setKbVersion, setAffectedScansCount, scanRef, fetchScan } = useClaimLoomWorkspace();
  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900">
      {isWakingUp && <div role="status" className="bg-amber-50 px-6 py-1.5 text-center text-xs font-medium text-amber-900">Waking the audit engine. You can keep working while it connects.</div>}
      {scanResult?.reaudit?.needed && <div className="flex items-center justify-between bg-red-600 px-6 py-2 text-xs font-medium text-white"><span>Re-audit required: {scanResult.reaudit.note}</span><button type="button" onClick={handleReaudit} className="rounded bg-white px-2.5 py-1 font-semibold text-red-700 focus-visible:ring-2">Re-audit now</button></div>}
      {toastMessage && <div role="status" className="fixed bottom-5 right-5 z-50 rounded-lg bg-slate-900 px-4 py-2.5 text-xs text-white shadow-lg">{toastMessage}</div>}
      <header className="sticky top-0 z-40 border-b border-slate-200/80 bg-white/85 backdrop-blur-xl shadow-2xs print:hidden">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-indigo-700 text-sm font-bold text-white shadow-xs ring-1 ring-black/5">
              CL
            </div>
            <div>
              <h1 className="text-sm font-bold tracking-tight text-slate-900 leading-none">ClaimLoom</h1>
              <p className="text-[11px] text-slate-500 font-medium tracking-tight mt-0.5">Pre-publication brand governance</p>
            </div>
            <div
              className={`ml-2 inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold border backdrop-blur-md shadow-2xs transition-all ${
                isLive
                  ? "border-emerald-200 bg-emerald-50/90 text-emerald-800"
                  : "border-amber-200 bg-amber-50/90 text-amber-800"
              }`}
              aria-live="polite"
            >
              <span className="relative flex h-2 w-2">
                <span
                  className={`absolute inline-flex h-full w-full rounded-full opacity-75 ${
                    isLive ? "animate-ping bg-emerald-400" : "bg-amber-400"
                  }`}
                />
                <span
                  className={`relative inline-flex rounded-full h-2 w-2 ${
                    isLive ? "bg-emerald-500" : "bg-amber-500"
                  }`}
                />
              </span>
              <span>{isLive ? "Live Engine" : "Offline"}</span>
              <span className="text-[10px] font-normal opacity-70">KB v{kbVersion} · Rules v{rulesVersion}</span>
            </div>
          </div>

          {/* Apple-style Navigation Controls */}
          <div className="flex flex-wrap items-center gap-2.5 text-xs">
            {/* Brand Workspace Pill */}
            <div className="relative flex items-center rounded-full border border-slate-200/80 bg-white/90 px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs hover:border-slate-300 hover:bg-white transition-all backdrop-blur-md">
              <span className="mr-1.5 text-slate-400 text-xs">🏷️</span>
              <span className="text-[11px] font-medium text-slate-500 mr-1.5">Brand:</span>
              <select
                aria-label="Brand workspace"
                value={workspaceId}
                onChange={(e) => void handleWorkspaceChange(e.target.value as "default" | "custom_brand")}
                className="bg-transparent font-semibold text-slate-900 pr-4 appearance-none cursor-pointer focus:outline-none text-xs"
              >
                <option value="default">ClaimLoom Official</option>
                <option value="custom_brand">My Custom Brand Sandbox</option>
              </select>
              <span className="pointer-events-none absolute right-2.5 text-[9px] text-slate-400">▼</span>
            </div>

            {/* Apple Segmented Persona Control */}
            <div className="flex items-center rounded-full border border-slate-200/80 bg-slate-100/80 p-0.5 shadow-2xs backdrop-blur-md">
              {(
                [
                  { id: "Creator", label: "Creator", icon: "✍️", hint: "Draft & fix" },
                  { id: "Reviewer", label: "Reviewer", icon: "🛡️", hint: "Approve & sign" },
                  { id: "Admin", label: "Admin", icon: "⚡", hint: "Rules & radar" },
                ] as const
              ).map((item) => {
                const active = role === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => handleRoleChange(item.id)}
                    title={`${item.label}: ${item.hint}`}
                    className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold transition-all duration-150 ${
                      active
                        ? "bg-white text-slate-900 shadow-xs ring-1 ring-black/5"
                        : "text-slate-600 hover:text-slate-900 hover:bg-white/40"
                    }`}
                  >
                    <span className="text-xs">{item.icon}</span>
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </div>

            {/* Reset Button */}
            <button
              type="button"
              aria-label="Reset workspace"
              onClick={handleResetDemo}
              title="Reset workspace demo state and sample copy"
              className="flex items-center gap-1.5 rounded-full border border-slate-200/80 bg-white/90 hover:bg-slate-100 active:scale-95 px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs hover:shadow-xs transition-all duration-150 backdrop-blur-md"
            >
              <span className="text-xs text-slate-500 transition-transform duration-300 hover:rotate-180">↺</span>
              <span>Reset</span>
            </button>

            {/* Chrome Extension Pill */}
            <button
              type="button"
              onClick={() => setShowExtensionModal(true)}
              className="flex items-center gap-1.5 rounded-full border border-blue-200/80 bg-blue-50/80 hover:bg-blue-100 active:scale-95 px-3.5 py-1.5 text-xs font-semibold text-blue-800 shadow-2xs hover:shadow-xs transition-all duration-150 backdrop-blur-md"
            >
              <span>🧩</span>
              <span>Chrome Extension</span>
            </button>
          </div>
        </div>

        {/* Apple Segmented Tabs */}
        <div className="mx-auto max-w-7xl px-6 pb-2.5">
          <nav
            role="tablist"
            aria-label="Workspace tabs"
            className="inline-flex items-center gap-1 rounded-2xl bg-slate-100/80 p-1 border border-slate-200/60 shadow-2xs backdrop-blur-md"
          >
            {TABS.map((t: { id: Tab; label: string }) => {
              const active = activeTab === t.id;
              const badge =
                t.id === "studio"
                  ? issues.length
                    ? String(issues.length)
                    : null
                  : t.id === "vault"
                  ? `v${kbVersion}`
                  : null;
              return (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => setActiveTab(t.id)}
                  className={`flex items-center gap-2 rounded-xl px-4 py-1.5 text-xs font-semibold transition-all duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 ${
                    active
                      ? "bg-white text-slate-900 shadow-xs ring-1 ring-black/5"
                      : "text-slate-600 hover:text-slate-900 hover:bg-white/40"
                  }`}
                >
                  <span>{t.label}</span>
                  {badge && (
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                        active ? "bg-blue-50 text-blue-700" : "bg-slate-200/80 text-slate-600"
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
          <button type="button" aria-label="Dismiss error" onClick={() => setErrorBanner(null)} className="shrink-0 font-semibold hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600">
            Dismiss
          </button>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.docx,.md,.markdown,.txt,.png,.jpg,.jpeg,.webp"
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
                currentRole={role}
                hint={signoffHint}
                canApprove={canApprove}
                isApproved={isApproved}
                onApprove={handleApprove}
                onViewCertificate={openCert}
                scanId={scanResult?.scan_id}
                onReaudit={handleActivityReaudit}
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
                onOverride={handleOverride}
                onSample={loadSample}
              />            </div>
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
            workspaceId={workspaceId}
            onDataLoaded={(loadedRules, loadedChunks, nextRulesVersion, nextKbVersion) => { setRules(loadedRules); setKbChunks(loadedChunks); setRulesVersion(nextRulesVersion); setKbVersion(nextKbVersion); }}
            onAffected={async (count, ids) => { setAffectedScansCount(count); const current = scanRef.current; if (current && ids.includes(current.scan_id)) { try { setScanResult(await fetchScan(current.scan_id)); } catch { /* retain current view if refresh is unavailable */ } } }}
          />
        </div>

        <div className={activeTab === "radar" ? "block" : "hidden"}>
          <RadarTab workspaceId={workspaceId} />
        </div>
      </main>

      {showCert && scanResult && (
        <CertificateModal scan={scanResult} role={role} signature={signature} publicKey={certificatePublicKey} onClose={closeCert} />
      )}

      <ExtensionModal
        isOpen={showExtensionModal}
        onClose={() => setShowExtensionModal(false)}
        defaultChannel={channel}
        defaultWorkspace={workspaceId}
      />
    </div>
  );
}
