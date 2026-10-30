"use client";

import { useClaimLoomWorkspace } from "../lib/useClaimLoomWorkspace";

import EditorCard from "../components/EditorCard";
import SignoffCard from "../components/SignoffCard";
import ResultsPanel from "../components/ResultsPanel";
import CanvasTab from "../components/CanvasTab";
import VaultTab from "../components/VaultTab";
import RadarTab from "../components/RadarTab";
import CertificateModal from "../components/CertificateModal";

import { Role, Tab, btnGhost, selectCls } from "../lib/ui";

export default function ClaimLoomWorkspace() {
  const { TABS, activeTab, setActiveTab, role, workspaceId, channel, setChannel, isLive, isWakingUp, kbVersion, rulesVersion, editorText, setEditorText, originalText, isScanning, scanStep, scanResult, setScanResult, scanOrigin, selectedIssueId, setSelectedIssueId, currentPage, setCurrentPage, errorBanner, setErrorBanner, toastMessage, showCert, signature, certificatePublicKey, kbChunks, affectedScansCount, rules, fileInputRef, issues, canApprove, isApproved, signoffHint, handleReaudit, handleWorkspaceChange, handleRoleChange, handleResetDemo, handleFileUpload, handleRunTextAudit, handleUploadClick, loadSample, handleApprove, openCert, closeCert, handleActivityReaudit, handleLocate, handleAcceptFix, handleOverride, handleSimulatePriceSync, setRules, setKbChunks, setRulesVersion, setKbVersion, setAffectedScansCount, scanRef, fetchScan } = useClaimLoomWorkspace();
  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900">
      {isWakingUp && <div role="status" className="bg-amber-50 px-6 py-1.5 text-center text-xs font-medium text-amber-900">Waking the audit engine. You can keep working while it connects.</div>}
      {scanResult?.reaudit?.needed && <div className="flex items-center justify-between bg-red-600 px-6 py-2 text-xs font-medium text-white"><span>Re-audit required: {scanResult.reaudit.note}</span><button type="button" onClick={handleReaudit} className="rounded bg-white px-2.5 py-1 font-semibold text-red-700 focus-visible:ring-2">Re-audit now</button></div>}
      {toastMessage && <div role="status" className="fixed bottom-5 right-5 z-50 rounded-lg bg-slate-900 px-4 py-2.5 text-xs text-white shadow-lg">{toastMessage}</div>}
      <header className="border-b border-slate-200 bg-white print:hidden">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-3">
          <div className="flex items-center gap-3"><div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600 text-sm font-bold text-white">CL</div><div><h1 className="text-base font-bold">ClaimLoom</h1><p className="text-xs text-slate-500">Brand governance and claim verification</p></div>
            <span className={`ml-2 inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${isLive ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-800"}`} aria-live="polite">{isLive ? "🟢 LIVE ENGINE (Neon + FastAPI)" : "🟡 OFFLINE DEMO FALLBACK (Read-Only)"}<span className="font-normal">KB v{kbVersion}, Rules v{rulesVersion}</span></span>
          </div>
          <div className="flex flex-wrap items-center gap-4 text-xs text-slate-600">
            <label className="flex items-center gap-2">Brand<select aria-label="Brand workspace" value={workspaceId} onChange={(e) => void handleWorkspaceChange(e.target.value as "default" | "custom_brand")} className={selectCls}><option value="default">ClaimLoom Official</option><option value="custom_brand">My Custom Brand Sandbox</option></select></label>
            <label className="flex items-center gap-2">Persona<select aria-label="Active role" value={role} onChange={(e) => handleRoleChange(e.target.value as Role)} className={selectCls}><option value="Creator">Creator: draft and fix</option><option value="Reviewer">Reviewer: approve and sign</option><option value="Admin">Admin: rules and radar</option></select></label>
            <button type="button" aria-label="Reset workspace" onClick={handleResetDemo} className={btnGhost}>Reset</button>
          </div>
        </div>
        <div className="mx-auto max-w-7xl overflow-x-auto px-6"><nav role="tablist" aria-label="Workspace" className="flex min-w-max gap-6">{TABS.map((t: { id: Tab; label: string }) => { const active = activeTab === t.id; const badge = t.id === "studio" ? (issues.length ? String(issues.length) : null) : t.id === "vault" ? `v${kbVersion}` : null; return <div key={t.id}>
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={active}
                  onClick={() => setActiveTab(t.id)}
                  className={`flex items-center gap-2 border-b-2 py-3 text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600 ${
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
                </button>{badge && <span className="sr-only">{badge}</span>}</div>; })}
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
    </div>
  );
}
