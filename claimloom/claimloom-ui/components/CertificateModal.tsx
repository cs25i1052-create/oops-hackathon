"use client";

import React, { useEffect, useState } from "react";
import { ScanVerification, verifyScan } from "../lib/client";
import type { ScanResponse } from "../lib/schema";
import { btnGhost, btnPrimary, Role } from "../lib/ui";

interface Props {
  scan: ScanResponse;
  role: Role;
  signature: { value: string; live: boolean; entry_hash?: string; text_sha256?: string; prev_hash?: string; reviewer?: string };
  publicKey?: string | null;
  onClose: () => void;
}

export default function CertificateModal({ scan, role, signature, publicKey, onClose }: Props) {
  const [verification, setVerification] = useState<ScanVerification | null>(null);
  const [verifying, setVerifying] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Sign-off certificate"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 print:absolute print:bg-white"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <h3 className="text-sm font-semibold">Sign-off certificate</h3>
          <button type="button" aria-label="Close certificate" onClick={onClose} className="text-xs text-slate-500 hover:text-slate-800 print:hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-600">
            Close
          </button>
        </div>
        <dl className="space-y-2 rounded-lg bg-slate-50 p-3 text-xs">
          <div className="flex justify-between gap-3">
            <dt className="font-semibold">Scan ID</dt>
            <dd>
              <code>{scan.scan_id}</code>
            </dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="font-semibold">Readiness</dt>
            <dd>{scan.readiness_score} / 100</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="font-semibold">Signed by role</dt>
            <dd>{role}</dd>
          </div>
          <div>
            <dt className="font-semibold">Ed25519 signature</dt>
            <dd>
              <code className="mt-1 block break-all rounded border border-slate-200 bg-white p-1.5 text-[10px]">
                {signature.value}
              </code>
            </dd>
          </div>
          {signature.entry_hash && <div><dt className="font-semibold">Entry hash</dt><dd><code className="break-all">{signature.entry_hash}</code></dd></div>}
          {signature.text_sha256 && <div><dt className="font-semibold">Text SHA-256</dt><dd><code className="break-all">{signature.text_sha256}</code></dd></div>}
          {signature.prev_hash && <div><dt className="font-semibold">Previous hash</dt><dd><code className="break-all">{signature.prev_hash}</code></dd></div>}
          {signature.reviewer && <div><dt className="font-semibold">Reviewer</dt><dd>{signature.reviewer}</dd></div>}
          {publicKey && <div><dt className="font-semibold">Public key</dt><dd><code className="break-all">{publicKey}</code></dd></div>}
        </dl>
        <p className={`text-xs font-medium ${signature.live ? "text-emerald-700" : "text-amber-700"}`}>
          {signature.live
            ? "Signature issued by the live engine."
            : "No live signature is available for this offline scan."}
        </p>
        <div className="flex justify-end gap-2 print:hidden">
          <button type="button" disabled={verifying || !signature.live} onClick={async () => { setVerifying(true); try { setVerification(await verifyScan(scan.scan_id)); } catch (e) { setVerification({ error: e instanceof Error ? e.message : "Verification failed" }); } finally { setVerifying(false); } }} className={btnGhost}>{verifying ? "Verifying…" : "Verify signature"}</button>
          <button type="button" onClick={onClose} className={btnGhost}>
            Close
          </button>
          <button type="button" onClick={() => window.print()} className={btnPrimary}>
            Print or save as PDF
          </button>
        </div>
        {verification && (
          <div
            className={`rounded-xl border p-3.5 text-xs transition-all ${
              verification.error
                ? "border-rose-200 bg-rose-50/80 text-rose-800"
                : verification.valid && !verification.tampered
                ? "border-emerald-200 bg-emerald-50/70 text-emerald-950 shadow-sm"
                : "border-amber-200 bg-amber-50/80 text-amber-900"
            }`}
            aria-live="polite"
          >
            {verification.error ? (
              <div className="flex items-center gap-2">
                <span className="font-bold text-rose-600">✕</span>
                <span>{verification.error}</span>
              </div>
            ) : verification.valid && !verification.tampered ? (
              <div className="space-y-1.5">
                <div className="flex items-center gap-2 font-semibold text-emerald-800">
                  <span className="flex h-4 w-4 items-center justify-center rounded-full bg-emerald-600 text-[10px] text-white">
                    ✓
                  </span>
                  <span>Cryptographically Verified &amp; Immutable</span>
                </div>
                <div className="grid grid-cols-2 gap-x-2 gap-y-1 pt-1 text-[11px] text-emerald-900/80">
                  <div>
                    <span className="font-medium text-emerald-950">Ed25519 Signature:</span> Valid
                  </div>
                  <div>
                    <span className="font-medium text-emerald-950">Audit Chain:</span> Intact &amp; Valid
                  </div>
                  <div>
                    <span className="font-medium text-emerald-950">Tampered:</span> No
                  </div>
                  <div>
                    <span className="font-medium text-emerald-950">Status:</span> Live Signed
                  </div>
                </div>
                {verification.certificate?.entry_hash && (
                  <div className="break-all pt-1 text-[10px] text-emerald-800/80">
                    <span className="font-medium text-emerald-950">Entry hash:</span>{" "}
                    <code>{verification.certificate.entry_hash}</code>
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-1 text-amber-900">
                <div className="flex items-center gap-2 font-semibold text-amber-800">
                  <span className="text-amber-600">⚠</span>
                  <span>Verification Discrepancy Detected</span>
                </div>
                <p className="text-[11px]">
                  Valid: {String(verification.valid)} · Tampered: {String(verification.tampered)} · Chain: {String(verification.chain_valid)}
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
