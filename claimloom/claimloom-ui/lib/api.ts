import { ScanResponse, ScanResponseSchema } from "./schema";

export const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
).replace(/\/+$/, "");

interface SessionResponse { token: string; role: string; name: string; workspace_id: string; }
interface ApiError { detail?: string | Array<{ loc?: Array<string | number>; msg?: string }>; message?: string; }

export async function ensureSessionToken(role: "Creator" | "Reviewer" | "Admin" = "Reviewer", name = "Judge Reviewer", workspace_id?: string): Promise<SessionResponse> {
  const ws = workspace_id ?? (typeof window !== "undefined" ? localStorage.getItem("cl_workspace") || "default" : "default");
  const res = await fetch(`${API_BASE}/api/session`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role, name, workspace_id: ws }) });
  if (!res.ok) throw new Error(`Could not establish ${role} session (HTTP ${res.status})`);
  const data = await res.json();
  localStorage.setItem("cl_token", data.token);
  localStorage.setItem("cl_role", data.role || role);
  localStorage.setItem("cl_workspace", data.workspace_id || ws);
  localStorage.setItem("cl_name", data.name || name);
  return data;
}

export function getAuthHeaders(extra: Record<string, string> = {}): Record<string, string> {
  if (typeof window === "undefined") return extra;
  const token = localStorage.getItem("cl_token") || "";
  const workspace = localStorage.getItem("cl_workspace") || "default";
  const role = localStorage.getItem("cl_role") || "Reviewer";
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    "X-Workspace-Id": workspace,
    "X-Demo-Role": role,
    ...extra,
  };
}

function formatApiError(errObj: ApiError | null, status: number): string {
  if (!errObj) return `HTTP Error ${status}`;
  if (typeof errObj.detail === "string") return errObj.detail;
  if (Array.isArray(errObj.detail)) {
    return errObj.detail
      .map((e) => `${e.loc ? e.loc.join(".") + ": " : ""}${e.msg || JSON.stringify(e)}`)
      .join("; ");
  }
  if (typeof errObj.message === "string") return errObj.message;
  return `Request failed with status ${status}`;
}

export async function runTextScan(
  text: string,
  channel: string = "general",
  workspaceId: string = "default"
): Promise<ScanResponse> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 35000);

  try {
    const res = await fetch(`${API_BASE}/api/scan-text`, {
      method: "POST",
      headers: getAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ text, channel, workspace_id: workspaceId }),
      signal: controller.signal,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => null);
      throw new Error(formatApiError(err, res.status));
    }

    const raw = await res.json();
    return ScanResponseSchema.parse(raw);
  } finally {
    clearTimeout(timeout);
  }
}

export async function uploadAssetForScan(
  endpoint: "/api/scan-pdf" | "/api/scan-image" | "/api/scan-doc",
  file: File,
  channel: string = "general",
  workspaceId: string = "default"
): Promise<ScanResponse> {
  if (file.size > 5 * 1024 * 1024) {
    throw new Error("File exceeds the 5 MB free-tier safety limit. Please upload a file under 5 MB.");
  }

  const formData = new FormData();
  formData.append("file", file); // Must be named "file"
  formData.append("channel", channel);
  formData.append("workspace_id", workspaceId);

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 45000);

  try {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      method: "POST",
      headers: getAuthHeaders(), // Never manually set Content-Type on FormData!
      body: formData,
      signal: controller.signal,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => null);
      throw new Error(formatApiError(err, res.status));
    }

    const raw = await res.json();
    return ScanResponseSchema.parse(raw);
  } finally {
    clearTimeout(timeout);
  }
}

export async function logFlagAction(scanId: string, ruleId: number, action: "Accepted" | "Dismissed" | "Overridden", reason: string = ""): Promise<void> {
  try {
    await fetch(`${API_BASE}/api/flag-action`, {
      method: "POST",
      headers: getAuthHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ scan_id: scanId, rule_id: ruleId, action, reason }),
    });
  } catch {
    // Ignore network errors in offline mode
  }
}

export function syncScanIdToUrl(scanId: string, resultData: ScanResponse) {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  url.searchParams.set("scan_id", scanId);
  window.history.replaceState({}, "", url.toString());
  localStorage.setItem("cl_last_scan", JSON.stringify(resultData));
}
