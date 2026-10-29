const $ = (id) => document.getElementById(id);

async function loadSettings() {
  const saved = await chrome.storage.sync.get({ api: "", channel: "general" });
  $("api").value = saved.api;
  $("channel").value = saved.channel;
}

function issueCard(issue) {
  const card = document.createElement("article");
  card.className = "issue";
  const title = document.createElement("strong");
  title.textContent = `${issue.severity || "Issue"} · ${issue.violation_type || "Governance"}`;
  const detail = document.createElement("span");
  detail.textContent = `${issue.flagged_text || "Flagged copy"} → ${issue.suggested_fix || "Review suggested fix"}`;
  card.append(title, detail);
  return card;
}

async function scanSelectedText() {
  const button = $("scan");
  const status = $("status");
  const results = $("results");
  button.disabled = true;
  results.replaceChildren();
  try {
    const api = $("api").value.trim().replace(/\/+$/, "");
    const channel = $("channel").value;
    if (!api) throw new Error("Enter your ClaimLoom backend URL first.");
    await chrome.storage.sync.set({ api, channel });
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) throw new Error("Could not find the active browser tab.");
    const [selection] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => window.getSelection()?.toString() || "",
    });
    const text = selection?.result?.trim();
    if (!text) throw new Error("Select some copy on the page before scanning.");
    status.textContent = "Scanning selected copy…";
    const response = await fetch(`${api}/api/scan-text`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Workspace-Id": "default" },
      body: JSON.stringify({ text, channel, workspace_id: "default" }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || `Scan failed (${response.status}).`);
    const score = document.createElement("p");
    score.className = "score";
    score.textContent = `Readiness score: ${data.readiness_score}/100 · ${data.status}`;
    results.append(score);
    for (const issue of data.issues || []) results.append(issueCard(issue));
    status.textContent = data.issues?.length ? `${data.issues.length} issue(s) found.` : "No issues found in the selected copy.";
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : "Unable to scan selected copy.";
  } finally {
    button.disabled = false;
  }
}

$("scan").addEventListener("click", scanSelectedText);
loadSettings();
