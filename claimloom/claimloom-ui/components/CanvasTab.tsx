"use client";

import React, { memo, useState } from "react";
import type { Issue, ScanResponse } from "../lib/schema";
import { pageImageUrl, redlineUrl } from "../lib/client";
import { Card, Empty } from "./Common";
import { btnDark, btnGhost, btnPrimary, Origin, sevStyle } from "../lib/ui";

function SimulatedPage({ page }: { page: number }) {
  if (page !== 1) {
    return (
      <div className="aspect-[1/1.35] w-full space-y-3 bg-white p-8">
        <div className="text-xs text-slate-400">Page {page}</div>
        {[80, 95, 70, 88, 60].map((w, i) => (
          <div key={i} className="h-2 rounded bg-slate-100" style={{ width: `${w}%` }} />
        ))}
      </div>
    );
  }
  return (
    <div className="aspect-[1/1.35] w-full bg-white p-8 text-slate-900 flex flex-col justify-between">
      <div>
        <div className="mb-6 flex items-center justify-between border-b border-slate-200 pb-2 text-xs">
          <span className="font-bold text-blue-900">ClaimLoom Enterprise Brochure</span>
          <span className="text-slate-400">Page 1</span>
        </div>
        <h3 className="mb-3 text-lg font-bold">Marketing Governance</h3>
        <p className="mb-4 text-xs text-slate-700">
          Get our ClaimLoom software for <span className="font-bold">guaranteed 100% results!</span>
        </p>
        <div className="rounded border border-slate-200 bg-slate-50 p-3 text-xs font-bold">
          Pro Plan costs $15/month
        </div>
      </div>
      
      {/* THIS WAS MISSING: The low-contrast footer text the bounding box is targeting */}
      <div className="border-t border-slate-200 pt-2 text-[10px] text-slate-400">
        Footer Disclaimer: 7.5pt font, Contrast 2.8:1
      </div>
    </div>
  );
}


interface Props {
  scanResult: ScanResponse | null;
  origin: Origin;
  currentPage: number;
  onPageChange: (page: number) => void;
  selectedIssueId: string | null;
  onSelectIssue: (id: string) => void;
  onResolve: (issue: Issue) => void;
  onUploadClick: () => void;
  onSample: (kind: "violation" | "clean" | "brochure") => void;
}

function CanvasTab({
  scanResult,
  origin,
  currentPage,
  onPageChange,
  selectedIssueId,
  onSelectIssue,
  onResolve,
  onUploadClick,
  onSample,
}: Props) {
  const [failedScanId, setFailedScanId] = useState<string | null>(null);

  const positioned = scanResult?.issues.filter((i) => i.bbox && i.bbox.length >= 4) ?? [];

  if (!scanResult || (scanResult.input_type === "text" && positioned.length === 0)) {
    return (
      <Empty
        title="No document on the canvas"
        body="Upload a PDF or image to see findings highlighted on the page, or load the sample brochure."
      >
        <button type="button" onClick={onUploadClick} className={btnPrimary}>
          Upload a document
        </button>
        <button type="button" onClick={() => onSample("brochure")} className={btnGhost}>
          Load sample brochure
        </button>
      </Empty>
    );
  }

  const pageCount = Math.max(1, scanResult.page_count);
  const useRealPage =
    origin === "live" &&
    (scanResult.input_type === "pdf" || scanResult.input_type === "image") &&
    failedScanId !== scanResult.scan_id;
  const onThisPage = positioned.filter((i) => i.page == null || i.page === currentPage);

  const select = (issue: Issue) => {
    onSelectIssue(issue.id);
    if (issue.page) onPageChange(issue.page);
  };

  return (
    <div className="grid items-start gap-6 lg:grid-cols-12">
      <Card className="bg-slate-100 p-5 lg:col-span-7">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-xs text-slate-600">
            <button
              type="button"
              onClick={() => onPageChange(Math.max(1, currentPage - 1))}
              disabled={currentPage <= 1}
              className={btnGhost}
              aria-label="Previous page"
            >
              Prev
            </button>
            <span className="font-medium">
              Page {currentPage} of {pageCount}
            </span>
            <button
              type="button"
              onClick={() => onPageChange(Math.min(pageCount, currentPage + 1))}
              disabled={currentPage >= pageCount}
              className={btnGhost}
              aria-label="Next page"
            >
              Next
            </button>
          </div>
          {origin === "live" && (
            <a
              href={redlineUrl(scanResult.scan_id)}
              target="_blank"
              rel="noopener noreferrer"
              className={btnPrimary}
            >
              Download redlined PDF
            </a>
          )}
        </div>

        <div className="relative mx-auto w-full max-w-[520px] overflow-hidden border border-slate-300 bg-white shadow-md">
          {useRealPage ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={pageImageUrl(scanResult.scan_id, currentPage)}
              alt={`Page ${currentPage} of the scanned document`}
              decoding="async"
              onError={() => setFailedScanId(scanResult.scan_id)}
              className="block w-full"
            />
          ) : (
            <SimulatedPage page={currentPage} />
          )}

          {onThisPage.map((issue) => {
            const [x0, y0, x1, y1] = issue.bbox as number[];
            return (
              <button
                key={issue.id}
                type="button"
                aria-label={`Select finding: ${issue.rule_cited}`}
                onClick={() => onSelectIssue(issue.id)}
                style={{
                  position: "absolute",
                  left: `${x0 * 100}%`,
                  top: `${y0 * 100}%`,
                  width: `${(x1 - x0) * 100}%`,
                  height: `${(y1 - y0) * 100}%`,
                }}
                className={`rounded border-2 transition focus-visible:outline-2 focus-visible:outline-blue-600 ${
                  sevStyle(issue.severity).box
                } ${selectedIssueId === issue.id ? "z-10 ring-4 ring-blue-500/50" : ""}`}
              />
            );
          })}
        </div>

        {!useRealPage && (
          <p className="mt-3 text-center text-xs text-slate-500">
            {origin === "live" ? "Page image unavailable. Showing a simulated layout." : "Showing a simulated sample page."}
          </p>
        )}
      </Card>

      <div className="space-y-3 lg:col-span-5">
        <h2 className="text-base font-semibold">Findings on this document</h2>
        {positioned.length === 0 ? (
          <p className="text-sm text-slate-500">No findings with a position on the page.</p>
        ) : (
          positioned.map((issue) => {
            const selected = selectedIssueId === issue.id;
            return (
              <div
                key={issue.id}
                role="button"
                tabIndex={0}
                onClick={() => select(issue)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    select(issue);
                  }
                }}
                className={`cursor-pointer rounded-xl border p-4 transition focus-visible:outline-2 focus-visible:outline-blue-600 ${
                  selected ? "border-blue-600 bg-blue-50/50 shadow-sm" : "border-slate-200 bg-white hover:border-slate-300"
                }`}
              >
                <div className="mb-1 flex items-center gap-2 text-sm font-semibold">
                  <span className={`h-2 w-2 shrink-0 rounded-full ${sevStyle(issue.severity).dot}`} />
                  {issue.rule_cited}
                </div>
                <p className="mb-3 text-xs text-slate-600">{issue.explanation}</p>
                <div className="flex items-center justify-between gap-2 border-t border-slate-100 pt-3">
                  <span className="text-xs font-medium text-emerald-700">Fix: {issue.suggested_fix}</span>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onResolve(issue);
                    }}
                    className={btnDark}
                  >
                    Resolve
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

export default memo(CanvasTab);