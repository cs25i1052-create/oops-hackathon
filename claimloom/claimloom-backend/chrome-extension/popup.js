const DEFAULT_API = "https://oops-hackathon.onrender.com";
const LOCAL_API = "http://localhost:8000";
const $ = (id) => document.getElementById(id);

async function loadSettings() {
  const saved = await chrome.storage.sync.get({ api: DEFAULT_API, localBackend: false, channel: "general", draft: "" });
  $("localBackend").checked = saved.localBackend;
  $("api").value = saved.localBackend ? LOCAL_API : (saved.api || DEFAULT_API);
  $("api").disabled = saved.localBackend;
  $("channel").value = saved.channel;
  $("draft").value = saved.draft;
}

function selectedTextOnPage() {
  return new Promise(async (resolve, reject) => {
    try {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab?.id) return reject(new Error("Could not find the active browser tab."));
      const [selection] = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => window.getSelection()?.toString() || "",
      });
      resolve(selection?.result?.trim() || "");
    } catch (error) { reject(error); }
  });
}

function appendPillars(container, pillars) {
  const section = document.createElement("section");
  section.className = "pillars";
  for (const [name, value] of Object.entries(pillars || {})) {
    const item = document.createElement("div");
    item.className = "pillar";
    item.textContent = `${name}: ${value}/100`;
    section.append(item);
  }
  container.append(section);
}

function issueCard(issue) {
  const card = document.createElement("article");
  card.className = "issue";
  const title = document.createElement("strong");
  title.textContent = `${issue.severity || "Issue"} · ${issue.violation_type || "Governance"}`;
  const detail = document.createElement("span");
  detail.textContent = `${issue.flagged_text || "Flagged copy"} → ${issue.suggested_fix || "Review suggested fix"}`;
  const copy = document.createElement("button");
  copy.type = "button";
  copy.textContent = "Copy Suggested Fix";
  copy.addEventListener("click", async () => {
    const fix = issue.suggested_fix || "";
    if (!fix) return;
    await navigator.clipboard.writeText(fix);
    copy.textContent = "Copied";
    window.setTimeout(() => { copy.textContent = "Copy Suggested Fix"; }, 1200);
  });
  card.append(title, detail, copy);
  return card;
}

async function scanCopy() {
  const button = $("scan");
  const status = $("status");
  const results = $("results");
  button.disabled = true;
  results.replaceChildren();
  try {
    const localBackend = $("localBackend").checked;
    const api = (localBackend ? LOCAL_API : $("api").value.trim()).replace(/\/+$/, "");
    const channel = $("channel").value;
    let text = $("draft").value.trim();
    if (!api) throw new Error("Enter a backend URL first.");
    let parsedApi;
    try { parsedApi = new URL(api); } catch { throw new Error("Enter a valid backend URL."); }
    if (!["http:", "https:"].includes(parsedApi.protocol)) throw new Error("Backend URL must use HTTP or HTTPS.");
    const originPattern = `${parsedApi.origin}/*`;
    const granted = await chrome.permissions.request({ origins: [originPattern] });
    if (!granted) throw new Error("Chrome permission for this backend was not granted.");
    if (!text) text = await selectedTextOnPage();
    if (!text) throw new Error("Select copy on the page or paste text into the box.");
    await chrome.storage.sync.set({ api, localBackend, channel, draft: $("draft").value });
    status.textContent = "Scanning copy…";
    const response = await fetch(`${api}/api/scan-text`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Workspace-Id": "default" },
      body: JSON.stringify({ text, channel, workspace_id: "default" }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Scan failed (${response.status}).`);
    const score = document.createElement("p");
    score.className = "score";
    score.textContent = `Readiness: ${data.readiness_score}/100 · ${data.status}`;
    results.append(score);
    appendPillars(results, data.pillar_scores);
    const issues = data.issues || [];
    for (const issue of issues) results.append(issueCard(issue));
    status.textContent = issues.length ? `${issues.length} issue(s) found.` : "No issues found in the copy.";
  } catch (error) {
    status.textContent = error instanceof Error ? error.message : "Unable to scan copy.";
  } finally {
    button.disabled = false;
  }
}

$("localBackend").addEventListener("change", () => {
  const local = $("localBackend").checked;
  $("api").disabled = local;
  if (local) $("api").value = LOCAL_API;
  else if ($("api").value === LOCAL_API) $("api").value = DEFAULT_API;
});
$("scan").addEventListener("click", scanCopy);
loadSettings();


