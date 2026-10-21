/* ============================================================
 * app.js — UI wiring. Talks to the backend ONLY through window.Api.
 * Every panel implements the four states: loading / empty / error / data.
 * ============================================================ */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const els = {
    healthBadge: $("healthBadge"),
    healthText: $("healthText"),
    uploadForm: $("uploadForm"),
    fileInput: $("fileInput"),
    fileName: $("fileName"),
    uploadBtn: $("uploadBtn"),
    uploadResult: $("uploadResult"),
    severity: $("severity"),
    requestId: $("requestId"),
    dateFrom: $("dateFrom"),
    dateTo: $("dateTo"),
    applyBtn: $("applyBtn"),
    resetBtn: $("resetBtn"),
    logBody: $("logBody"),
    logLoading: $("logLoading"),
    logEmpty: $("logEmpty"),
    logError: $("logError"),
    logErrorMsg: $("logErrorMsg"),
    logRetry: $("logRetry"),
    prevBtn: $("prevBtn"),
    nextBtn: $("nextBtn"),
    pageInfo: $("pageInfo"),
    statsLoading: $("statsLoading"),
    statsEmpty: $("statsEmpty"),
    statsError: $("statsError"),
    statsRetry: $("statsRetry"),
    statsList: $("statsList"),
  };

  const state = { page: 1, limit: window.Api.PAGE_SIZE };

  /* Escape user/server text before putting it in HTML (XSS safety). */
  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  function fmtTs(iso) {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? esc(iso) : d.toLocaleString();
  }

  function showOnly(...visible) {
    const all = [els.logLoading, els.logEmpty, els.logError, els.logBody];
    all.forEach((el) => el.classList.add("hidden"));
    visible.forEach((el) => el.classList.remove("hidden"));
  }

  /* ---------------- health ---------------- */
  async function loadHealth() {
    els.healthBadge.className = "health-badge health-unknown";
    els.healthText.textContent = "checking…";
    try {
      const h = await window.Api.getHealth();
      els.healthBadge.className = "health-badge health-ok";
      els.healthText.textContent = `${h.total_entries.toLocaleString()} entries`;
      els.healthBadge.title = `API ${h.status} · DB ${h.db} · last upload ${fmtTs(h.last_upload)}`;
    } catch (_) {
      els.healthBadge.className = "health-badge health-down";
      els.healthText.textContent = "API unreachable";
    }
  }

  /* ---------------- log table ---------------- */
  function currentFilters() {
    return {
      severity: els.severity.value,
      requestId: els.requestId.value.trim(),
      from: els.dateFrom.value,
      to: els.dateTo.value,
      page: state.page,
      limit: state.limit,
    };
  }

  async function loadLogs() {
    showOnly(els.logLoading);
    els.prevBtn.disabled = true;
    els.nextBtn.disabled = true;
    try {
      const data = await window.Api.getLogs(currentFilters());
      if (!data.entries.length) {
        showOnly(els.logEmpty);
      } else {
        els.logBody.innerHTML = data.entries
          .map(
            (e) => `<tr>
              <td class="ts" title="${esc(e.timestamp)}">${fmtTs(e.timestamp)}</td>
              <td><span class="sev sev-${esc(e.severity)}">${esc(e.severity)}</span></td>
              <td>${esc(e.service)}</td>
              <td>${e.request_id ? `<span class="req">${esc(e.request_id)}</span>` : `<span class="req-none">—</span>`}</td>
              <td>${esc(e.message)}</td>
            </tr>`
          )
          .join("");
        showOnly(els.logBody);
      }
      const pages = Math.max(1, Math.ceil(data.total / data.limit));
      els.pageInfo.textContent = `Page ${data.page} of ${pages} · ${data.total.toLocaleString()} entries`;
      els.prevBtn.disabled = data.page <= 1;
      els.nextBtn.disabled = data.page >= pages;
    } catch (err) {
      els.logErrorMsg.textContent = `Could not load log entries: ${err.message} `;
      showOnly(els.logError);
      els.pageInfo.textContent = "";
    }
  }

  /* ---------------- recurring errors ---------------- */
  function showStats(...visible) {
    [els.statsLoading, els.statsEmpty, els.statsError, els.statsList]
      .forEach((el) => el.classList.add("hidden"));
    visible.forEach((el) => el.classList.remove("hidden"));
  }

  async function loadStats() {
    showStats(els.statsLoading);
    try {
      const data = await window.Api.getErrorStats(8);
      if (!data.errors.length) {
        showStats(els.statsEmpty);
        return;
      }
      els.statsList.innerHTML = data.errors
        .map(
          (g) => `<li class="stat-item" data-severity="${esc(g.severity)}">
            <div class="stat-top">
              <p class="stat-msg"><span class="sev sev-${esc(g.severity)}">${esc(g.severity)}</span> ${esc(g.message)}</p>
              <span class="stat-count">×${g.count}</span>
            </div>
            <div class="stat-meta">first ${fmtTs(g.first_seen)} · last ${fmtTs(g.last_seen)}</div>
            <div class="chips">
              ${g.sample_request_ids.map((id) => `<button class="chip" data-req="${esc(id)}" title="Trace this request">${esc(id)}</button>`).join("")}
            </div>
          </li>`
        )
        .join("");
      showStats(els.statsList);
    } catch (err) {
      showStats(els.statsError);
    }
  }

  /* ---------------- upload ---------------- */
  function renderUploadReport(r) {
    const lines = `
      <div>
        <span class="status-pill ${esc(r.status)}">${esc(r.status)}</span>
        <strong>${r.parsed_lines}/${r.total_lines}</strong> lines parsed
        · <strong>${r.failed_lines}</strong> skipped
      </div>
      ${r.errors?.length ? `<ul class="upload-errors">
        ${r.errors.map((e) => `<li>line ${esc(e.line)}: ${esc(e.reason)}</li>`).join("")}
      </ul>` : ""}`;
    els.uploadResult.className = `upload-result ${esc(r.status)}`;
    els.uploadResult.innerHTML = lines;
  }

  function renderUploadError(msg) {
    els.uploadResult.className = "upload-result failed";
    els.uploadResult.innerHTML = `<span class="status-pill failed">failed</span>${esc(msg)}`;
  }

  els.fileInput.addEventListener("change", () => {
    const f = els.fileInput.files[0];
    els.fileName.textContent = f ? `${f.name} (${(f.size / 1024).toFixed(1)} KB)` : "Choose a .log / .jsonl file…";
    els.uploadBtn.disabled = !f;
    els.uploadResult.classList.add("hidden");
  });

  els.uploadForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = els.fileInput.files[0];
    if (!f) return;
    els.uploadBtn.disabled = true;
    els.uploadBtn.textContent = "Uploading…";
    els.uploadResult.classList.add("hidden");
    try {
      const report = await window.Api.uploadLogs(f);
      renderUploadReport(report);
      loadHealth();
      loadStats();
      state.page = 1;
      loadLogs();
    } catch (err) {
      renderUploadError(err.message);
    } finally {
      els.uploadBtn.disabled = false;
      els.uploadBtn.textContent = "Upload";
    }
  });

  /* ---------------- filter + stats interactions ---------------- */
  els.applyBtn.addEventListener("click", () => { state.page = 1; loadLogs(); });
  els.requestId.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { state.page = 1; loadLogs(); }
  });
  els.resetBtn.addEventListener("click", () => {
    els.severity.value = "";
    els.requestId.value = "";
    els.dateFrom.value = "";
    els.dateTo.value = "";
    state.page = 1;
    loadLogs();
  });
  els.prevBtn.addEventListener("click", () => { state.page -= 1; loadLogs(); });
  els.nextBtn.addEventListener("click", () => { state.page += 1; loadLogs(); });
  els.logRetry.addEventListener("click", loadLogs);
  els.statsRetry.addEventListener("click", loadStats);

  // Click a recurring-error card → filter table to that severity.
  // Click a request-ID chip → trace that exact request.
  els.statsList.addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (chip) {
      els.requestId.value = chip.dataset.req;
      els.severity.value = "";
      state.page = 1;
      loadLogs();
      return;
    }
    const item = e.target.closest(".stat-item");
    if (item) {
      els.severity.value = item.dataset.severity;
      els.requestId.value = "";
      state.page = 1;
      loadLogs();
    }
  });

  /* ---------------- init ---------------- */
  loadHealth();
  loadStats();
  loadLogs();
})();
