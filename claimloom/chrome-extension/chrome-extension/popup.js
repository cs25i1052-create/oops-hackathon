const draftEl = document.getElementById("draftText");
const channelEl = document.getElementById("channel");
const apiUrlEl = document.getElementById("apiUrl");
const scanBtn = document.getElementById("scanBtn");
const outputEl = document.getElementById("output");

// 1. On popup open, grab highlighted text from the active browser tab
chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const activeTab = tabs[0];
    if (!activeTab || !activeTab.id || activeTab.url?.startsWith("chrome://")) return;

    chrome.scripting.executeScript(
        {
            target: { tabId: activeTab.id },
            func: () => window.getSelection().toString().trim(),
        },
        (results) => {
            if (chrome.runtime.lastError) return;
            const selected = results && results[0] && results[0].result;
            if (selected) draftEl.value = selected;
        }
    );
});

// 2. Run scan against /api/scan-text
scanBtn.addEventListener("click", async () => {
    const text = draftEl.value.trim();
    const baseUrl = apiUrlEl.value.trim().replace(/\/+$/, "");
    if (!text) {
        outputEl.innerHTML = '<div class="status-msg">Please select or enter text to audit.</div>';
        return;
    }

    scanBtn.disabled = true;
    scanBtn.textContent = "Auditing...";
    outputEl.innerHTML = '<div class="status-msg">Checking Brand Rules & Truth Vault...</div>';

    try {
        const res = await fetch(`${baseUrl}/api/scan-text`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                text,
                channel: channelEl.value,
                workspace_id: "default",
            }),
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        renderResults(data);
    } catch (err) {
        outputEl.innerHTML = `<div class="status-msg" style="color:#fca5a5;">Error: ${err.message}. Check backend URL.</div>`;
    } finally {
        scanBtn.disabled = false;
        scanBtn.textContent = "Scan with ClaimLoom";
    }
});

function renderResults(data) {
    const issues = data.issues || [];
    let html = `
    <div class="score-bar">
      <span>Readiness: ${data.readiness_score}/100</span>
      <span style="color:${data.status === "approved" ? "#4ade80" : "#facc15"}">
        ${data.status.toUpperCase()}
      </span>
    </div>
  `;

    if (issues.length === 0) {
        html += '<div class="status-msg" style="color:#4ade80;">Zero violations found. Ready to publish!</div>';
    } else {
        issues.forEach((iss) => {
            const safeFix = (iss.suggested_fix || "").replace(/"/g, "&quot;");
            const safeFlag = (iss.flagged_text || "").replace(/"/g, "&quot;");
            html += `
        <div class="issue-card">
          <div><strong>[${iss.severity}]</strong> ${iss.rule_cited}</div>
          <div style="color:#cbd5e1;margin-top:3px;">Flagged: "${iss.flagged_text}"</div>
          <div class="issue-fix" data-flag="${safeFlag}" data-fix="${safeFix}">
            Apply Fix: "${iss.suggested_fix}"
          </div>
        </div>
      `;
        });
    }

    outputEl.innerHTML = html;

    outputEl.querySelectorAll(".issue-fix").forEach((btn) => {
        btn.addEventListener("click", () => {
            const flag = btn.getAttribute("data-flag");
            const fix = btn.getAttribute("data-fix");
            if (flag && fix) {
                draftEl.value = draftEl.value.replace(flag, fix);
                navigator.clipboard?.writeText(draftEl.value);
                btn.textContent = "Applied & Copied!";
            }
        });
    });
}