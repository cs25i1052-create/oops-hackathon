import dummyData from "./dummyData.json";
import { ScanResponseSchema, ScanResponse } from "./schema";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function scanText(
  text: string,
  mock: boolean,
  signal?: AbortSignal
): Promise<ScanResponse> {
  if (mock) {
    await new Promise((r) => setTimeout(r, 1200));
    const parsed = ScanResponseSchema.parse(dummyData);
    return {
      ...parsed,
      issues: parsed.issues.filter(
        (i) => i.violation_type !== "Visual" && text.includes(i.flagged_text)
      ),
    };
  }

  const res = await fetch(`${BASE_URL}/api/scan-text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal,
  });

  if (!res.ok) {
    throw new Error(`Text scan failed with status ${res.status}`);
  }

  const json = await res.json();
  return ScanResponseSchema.parse(json);
}

export async function scanImage(
  file: File,
  mock: boolean,
  signal?: AbortSignal
): Promise<ScanResponse> {
  if (mock) {
    await new Promise((r) => setTimeout(r, 1500));
    const parsed = ScanResponseSchema.parse(dummyData);
    return {
      ...parsed,
      issues: parsed.issues.filter((i) => i.violation_type === "Visual"),
    };
  }

  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${BASE_URL}/api/scan-image`, {
    method: "POST",
    body: formData,
    signal,
  });

  if (!res.ok) {
    throw new Error(`Image scan failed with status ${res.status}`);
  }

  const json = await res.json();
  return ScanResponseSchema.parse(json);
}