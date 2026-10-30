import { API_BASE, getAuthHeaders } from "./api";
import { ScanResponse, ScanResponseSchema } from "./schema";

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

interface ApprovalCertificate { signature?: string; entry_hash?: string; text_sha256?: string; prev_hash?: string | null; reviewer?: string; [field: string]: unknown; }
export interface ScanVerification { valid?: boolean; tampered?: boolean; chain_valid?: boolean; certificate?: { entry_hash?: string }; error?: string; }

async function fetchWithTimeout(url: string, init: RequestInit = {}, ms = 15000): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

export async function pingHealth(ms = 6000): Promise<boolean> {
  try {
    const res = await fetchWithTimeout(`${API_BASE}/ping`, {}, ms);
    return res.ok;
  } catch {
    return false;
  }
}

/** Polls /health while a free-tier host (Render) wakes up. */
export async function waitForEngine(isCancelled: () => boolean, attempts = 10): Promise<boolean> {
  for (let i = 0; i < attempts; i++) {
    if (isCancelled()) return false;
    if (await pingHealth()) return true;
    await sleep(3000);
  }
  return false;
}

function isTransient(e: unknown): boolean {
  if (e instanceof Error) {
    if (e.name === "AbortError" || e instanceof TypeError) return true;
    return /\b(502|503|504)\b/.test(e.message);
  }
  return false;
}

/** Retries once, but only while the engine is still waking up. */
export async function withColdStartRetry<T>(
  fn: () => Promise<T>,
  onRetry?: () => void,
  shouldRetry: () => boolean = () => true
): Promise<T> {
  try {
    return await fn();
  } catch (e) {
    if (!shouldRetry() || !isTransient(e)) throw e;
    onRetry?.();
    await sleep(5000);
    return fn();
  }
}

export async function fetchScan(scanId: string): Promise<ScanResponse> {
  const res = await fetchWithTimeout(
    `${API_BASE}/api/scans/${encodeURIComponent(scanId)}`,
    { headers: getAuthHeaders() },
    15000
  );
  if (!res.ok) throw new Error(`HTTP Error ${res.status}`);
  return ScanResponseSchema.parse(await res.json());
}

export async function approveScan(
  scanId: string,
  role: string,
  textSnapshot?: string
): Promise<{ approval: ApprovalCertificate | null; public_key: string | null; error: string | null }> {
  try {
    let versionNo: number | undefined;
    if (textSnapshot !== undefined) {
      const versionRes = await fetchWithTimeout(`${API_BASE}/api/scans/${encodeURIComponent(scanId)}/versions`, { method: "POST", headers: getAuthHeaders({ "Content-Type": "application/json" }), body: JSON.stringify({ text_snapshot: textSnapshot }) }, 15000);
      if (!versionRes.ok) return { approval: null, public_key: null, error: `Version save failed (HTTP ${versionRes.status})` };
      const versionData = await versionRes.json();
      versionNo = versionData.version_no;
    }
    const res = await fetchWithTimeout(
      `${API_BASE}/api/scans/${encodeURIComponent(scanId)}/approve`,
      {
        method: "POST",
        headers: getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ reviewer: role, role, ...(versionNo ? { version_no: versionNo } : {}) }),
      },
      15000
    );
    if (!res.ok) return { approval: null, public_key: null, error: `HTTP Error ${res.status}` };
    const data = await res.json() as { approval?: ApprovalCertificate; public_key?: string; signature?: string } & ApprovalCertificate;
    const approval = data.approval || data;
    return approval.signature
      ? { approval, public_key: data.public_key || null, error: null }
      : { approval: null, public_key: null, error: "The server did not return a signature" };
  } catch (e) {
    return { approval: null, public_key: null, error: e instanceof Error ? e.message : "Request failed" };
  }
}

export async function verifyScan(scanId: string): Promise<ScanVerification> {
  const response = await fetchWithTimeout(`${API_BASE}/api/verify/${encodeURIComponent(scanId)}`, { headers: getAuthHeaders() });
  if (!response.ok) throw new Error(`Verification failed (HTTP ${response.status})`);
  return response.json() as Promise<ScanVerification>;
}

export const pageImageUrl = (scanId: string, page: number) =>
  `${API_BASE}/api/scans/${encodeURIComponent(scanId)}/page/${page}.png`;

export const redlineUrl = (scanId: string) =>
  `${API_BASE}/api/scans/${encodeURIComponent(scanId)}/redline-pdf`;
