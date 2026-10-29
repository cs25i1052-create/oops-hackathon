"use client";

import React, { useEffect } from "react";
import type { ScanResponse } from "../lib/schema";
import { btnGhost, btnPrimary, Role } from "../lib/ui";

interface Props {
  scan: ScanResponse;
  role: Role;
  signature: { value: string; live: boolean };
  onClose: () => void;
}

export default function CertificateModal({ scan, role, signature, onClose }: Props) {
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
        </dl>
        <p className={`text-xs font-medium ${signature.live ? "text-emerald-700" : "text-amber-700"}`}>
          {signature.live
            ? "Signature issued by the live engine."
            : "Demo signature. This scan is not stored on the backend, so this is not a real signature."}
        </p>
        <div className="flex justify-end gap-2 print:hidden">
          <button type="button" onClick={onClose} className={btnGhost}>
            Close
          </button>
          <button type="button" onClick={() => window.print()} className={btnPrimary}>
            Print or save as PDF
          </button>
        </div>
      </div>
    </div>
  );
}