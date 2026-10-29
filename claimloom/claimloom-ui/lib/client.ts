import { API_BASE, getAuthHeaders } from "./api";
import { ScanResponse, ScanResponseSchema } from "./schema";

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

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
    const res = await fetchWithTimeout(`${API_BASE}/health`, {}, ms);
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
  role: string
): Promise<{ signature: string | null; error: string | null }> {
  try {
    const res = await fetchWithTimeout(
      `${API_BASE}/api/scans/${encodeURIComponent(scanId)}/approve`,
      {
        method: "POST",
        headers: getAuthHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ reviewer: role, role }),
      },
      15000
    );
    if (!res.ok) return { signature: null, error: `HTTP Error ${res.status}` };
    const data = (await res.json()) as { signature?: string };
    return data.signature
      ? { signature: data.signature, error: null }
      : { signature: null, error: "The server did not return a signature" };
  } catch (e) {
    return { signature: null, error: e instanceof Error ? e.message : "Request failed" };
  }
}

export const pageImageUrl = (scanId: string, page: number) =>
  `${API_BASE}/api/scans/${encodeURIComponent(scanId)}/page/${page}.png`;

export const redlineUrl = (scanId: string) =>
  `${API_BASE}/api/scans/${encodeURIComponent(scanId)}/redline-pdf`;