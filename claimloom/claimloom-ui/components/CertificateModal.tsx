"use client";

import React, { useEffect, useState } from "react";
import { verifyScan } from "../lib/client";
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
  const [verification, setVerification] = useState<any>(null);
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
          <button type="button" onClick={onClose} className="text-xs text-slate-500 hover:text-slate-800 print:hidden">
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
        {verification && <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs" aria-live="polite">{verification.error || <>Valid: {String(verification.valid)} · Tampered: {String(verification.tampered)} · Chain valid: {String(verification.chain_valid)} · Entry hash: <code className="break-all">{verification.certificate?.entry_hash || "—"}</code></>}</div>}
      </div>
    </div>
  );
}
