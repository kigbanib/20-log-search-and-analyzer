/* ============================================================
   Sift — Log Search & Analyzer · UI layer
   Talks to the backend ONLY through window.Api (the seam).
   Panels: health · timeline chart · upload · filter+table ·
   recurring errors · request trace drawer.
   ============================================================ */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const SEVS = ["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"];

  const els = {
    healthBadge: $("healthBadge"), healthText: $("healthText"),
    themeToggle: $("themeToggle"),
    bucketHour: $("bucketHour"), bucketDay: $("bucketDay"),
    chartLoading: $("chartLoading"), chart: $("chart"), chartEmpty: $("chartEmpty"), chartLegend: $("chartLegend"),
    uploadForm: $("uploadForm"), dropZone: $("dropZone"), fileInput: $("fileInput"),
    fileName: $("fileName"), uploadBtn: $("uploadBtn"), uploadResult: $("uploadResult"),
    severity: $("severity"), requestId: $("requestId"), dateFrom: $("dateFrom"), dateTo: $("dateTo"),
    applyBtn: $("applyBtn"), resetBtn: $("resetBtn"),
    logBody: $("logBody"), logSkeleton: $("logSkeleton"), logEmpty: $("logEmpty"),
    clearFiltersLink: $("clearFiltersLink"), logError: $("logError"), logErrorMsg: $("logErrorMsg"), logRetry: $("logRetry"),
    prevBtn: $("prevBtn"), nextBtn: $("nextBtn"), pageInfo: $("pageInfo"),
    statsLoading: $("statsLoading"), statsEmpty: $("statsEmpty"), statsError: $("statsError"),
    statsRetry: $("statsRetry"), statsList: $("statsList"),
    streakStrip: $("streakStrip"), streakChips: $("streakChips"),
    traceOverlay: $("traceOverlay"), traceIdBtn: $("traceIdBtn"), traceCopyLink: $("traceCopyLink"),
    traceClose: $("traceClose"), traceMeta: $("traceMeta"), traceLoading: $("traceLoading"),
    traceEmpty: $("traceEmpty"), traceError: $("traceError"), traceRetry: $("traceRetry"), traceSteps: $("traceSteps"),
  };

  const state = { page: 1, limit: window.Api.PAGE_SIZE, bucket: "hour", traceId: null };

  /* ---------------- helpers ---------------- */
  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }
  function fmtAbs(iso) {
    const d = new Date(iso);
    return Number.isNaN(d.getTime()) ? String(iso) : d.toLocaleString();
  }
  function fmtRel(iso) {
    const s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (Number.isNaN(s)) return "";
    if (s < 60) return `${Math.round(s)}s ago`;
    if (s < 3600) return `${Math.round(s / 60)}m ago`;
    if (s < 86400) return `${Math.round(s / 3600)}h ago`;
    return `${Math.round(s / 86400)}d ago`;
  }
  function humanizeDuration(ms) {
    const s = Math.round(ms / 1000);
    if (s < 1) return `${ms}ms`;
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    if (m < 60) return s % 60 ? `${m}m ${s % 60}s` : `${m}m`;
    return `${Math.floor(m / 60)}h ${m % 60}m`;
  }
  // ISO-8601 (UTC, 'Z') → the local "YYYY-MM-DDTHH:MM" format datetime-local wants.
  function toLocalInput(iso) {
    const d = new Date(iso);
    return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  }

  /* ---------------- theme ---------------- */
  function initTheme() {
    const saved = localStorage.getItem("sift-theme");
    document.documentElement.dataset.theme = saved || "dark";
  }
  els.themeToggle.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("sift-theme", next);
  });

  /* ---------------- deep links (shareable state) ---------------- */
  function readQuery() {
    const q = new URLSearchParams(location.search);
    if (q.get("severity")) els.severity.value = q.get("severity");
    if (q.get("request_id")) els.requestId.value = q.get("request_id");
    if (q.get("from")) els.dateFrom.value = q.get("from");
    if (q.get("to")) els.dateTo.value = q.get("to");
    return q;
  }
  function writeQuery() {
    const q = new URLSearchParams();
    if (els.severity.value) q.set("severity", els.severity.value);
    if (els.requestId.value.trim()) q.set("request_id", els.requestId.value.trim());
    if (els.dateFrom.value) q.set("from", els.dateFrom.value);
    if (els.dateTo.value) q.set("to", els.dateTo.value);
    if (state.traceId) q.set("trace", state.traceId);
    const url = q.toString() ? `?${q}` : location.pathname;
    history.replaceState(null, "", url);
  }

  /* ---------------- health ---------------- */
  async function loadHealth() {
    els.healthBadge.className = "health-badge health-unknown";
    els.healthText.textContent = "checking…";
    try {
      const h = await window.Api.getHealth();
      els.healthBadge.className = "health-badge health-ok";
      els.healthText.textContent = `operational · ${h.total_entries.toLocaleString()}`;
      els.healthBadge.title = `API ${h.status} · DB ${h.db} · last upload ${fmtAbs(h.last_upload)}`;
    } catch (_) {
      els.healthBadge.className = "health-badge health-down";
      els.healthText.textContent = "unreachable";
    }
  }

  /* ---------------- timeline chart ---------------- */
  function showChartState(mode) {
    els.chartLoading.classList.toggle("hidden", mode !== "loading");
    els.chart.classList.toggle("hidden", mode === "loading" || mode === "empty");
    els.chartEmpty.classList.toggle("hidden", mode !== "empty");
    els.chartLegend.classList.toggle("hidden", mode === "loading" || mode === "empty");
  }

  async function loadTimeline() {
    showChartState("loading");
    try {
      const data = await window.Api.getTimeline(state.bucket);
      const buckets = data.buckets || [];
      if (!buckets.length) { showChartState("empty"); return; }

      const totals = buckets.map((b) => SEVS.reduce((n, s) => n + (b[s] || 0), 0));
      const maxTotal = Math.max(1, ...totals);
      const label = (start) => {
        if (state.bucket === "day") return start;
        const d = new Date(start);
        return Number.isNaN(d.getTime()) ? start
          : d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) + " " +
            d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
      };

      els.chart.innerHTML = buckets.map((b, i) => {
        const parts = SEVS.filter((s) => b[s] > 0)
          .map((s) => `<span class="c-${s}" style="flex:${b[s]}"></span>`).join("");
        const tip = `${label(b.start)} — ` +
          SEVS.filter((s) => b[s]).map((s) => `${s[0]}:${b[s]}`).join("  ") +
          `  (${totals[i]})`;
        return `<div class="chart-col" style="height:${Math.max(2, (totals[i] / maxTotal) * 100)}%" title="${tip}">${parts}</div>`;
      }).join("");

      els.chartLegend.innerHTML = SEVS
        .filter((s) => buckets.some((b) => b[s] > 0))
        .map((s) => `<span><i class="c-${s}"></i>${s}</span>`).join("");
      showChartState("data");
    } catch (_) {
      showChartState("empty");
    }
  }

  els.bucketHour.addEventListener("click", () => setBucket("hour"));
  els.bucketDay.addEventListener("click", () => setBucket("day"));
  function setBucket(b) {
    state.bucket = b;
    els.bucketHour.classList.toggle("active", b === "hour");
    els.bucketDay.classList.toggle("active", b === "day");
    loadTimeline();
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

  function renderSkeleton() {
    const cells = ["22px", "80px", "56px", "90px", "86px", "55%"];
    els.logSkeleton.innerHTML = Array.from({ length: 8 }, () =>
      `<tr class="skel-row">${cells.map((w) => `<td><span class="skel-bar" style="width:${w}"></span></td>`).join("")}</tr>`
    ).join("");
    els.logSkeleton.classList.remove("hidden");
    els.logBody.innerHTML = "";
    [els.logEmpty, els.logError].forEach((el) => el.classList.add("hidden"));
  }

  async function loadLogs() {
    renderSkeleton();
    els.prevBtn.disabled = true;
    els.nextBtn.disabled = true;
    try {
      const data = await window.Api.getLogs(currentFilters());
      els.logSkeleton.classList.add("hidden");
      if (!data.entries.length) {
        els.logEmpty.classList.remove("hidden");
      } else {
        const offset = (data.page - 1) * data.limit;
        els.logBody.innerHTML = data.entries.map((e, i) => `<tr class="r-${esc(e.severity)}">
          <td class="n">${offset + i + 1}</td>
          <td class="ts" title="${esc(e.timestamp)}">${fmtRel(e.timestamp)}</td>
          <td><span class="sev sev-${esc(e.severity)}">${esc(e.severity)}</span></td>
          <td class="svc">${esc(e.service)}</td>
          <td>${e.request_id
            ? `<button class="req-chip" data-req="${esc(e.request_id)}" title="Trace ${esc(e.request_id)}">${esc(e.request_id)}</button>`
            : `<span class="req-none">—</span>`}</td>
          <td class="msg" title="Click to expand">${esc(e.message)}</td>
        </tr>`).join("");
      }
      const pages = Math.max(1, Math.ceil(data.total / data.limit));
      els.pageInfo.textContent = `page ${data.page}/${pages} · ${data.total.toLocaleString()} entries`;
      els.prevBtn.disabled = data.page <= 1;
      els.nextBtn.disabled = data.page >= pages;
    } catch (err) {
      els.logSkeleton.classList.add("hidden");
      els.logErrorMsg.textContent = `Could not load log entries: ${err.message} `;
      els.logError.classList.remove("hidden");
      els.pageInfo.textContent = "";
    }
  }

  // Row interactions: req chip → trace; message cell → expand/collapse.
  els.logBody.addEventListener("click", (e) => {
    const chip = e.target.closest(".req-chip");
    if (chip) { openTrace(chip.dataset.req); return; }
    const row = e.target.closest("tr");
    if (row) row.classList.toggle("expanded");
  });

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
      if (!data.errors.length) { showStats(els.statsEmpty); return; }
      const top = data.errors[0].count || 1;
      els.statsList.innerHTML = data.errors.map((g, i) => `<li class="stat-item" data-severity="${esc(g.severity)}">
        <span class="bar" style="width:${(g.count / top) * 100}%"></span>
        <div class="stat-top">
          <p class="stat-msg"><span class="stat-rank">#${i + 1}</span><i class="sev-dot c-${esc(g.severity)}"></i>${esc(g.message)}</p>
          <span class="stat-count">×${g.count}</span>
        </div>
        <div class="stat-meta">${esc(g.severity)} · first ${fmtRel(g.first_seen)} · last ${fmtRel(g.last_seen)}</div>
        <div class="chips">
          ${g.sample_request_ids.map((id) => `<button class="chip" data-req="${esc(id)}" title="Trace this request">${esc(id)}</button>`).join("")}
        </div>
      </li>`).join("");
      showStats(els.statsList);
    } catch (_) {
      showStats(els.statsError);
    }
  }

  els.statsList.addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (chip) { openTrace(chip.dataset.req); return; }
    const item = e.target.closest(".stat-item");
    if (item) {
      els.severity.value = item.dataset.severity;
      els.requestId.value = "";
      state.page = 1;
      writeQuery();
      loadLogs();
    }
  });

  /* ---------------- upload ---------------- */
  function renderUploadReport(r) {
    const total = r.total_lines || 1;
    els.uploadResult.className = "upload-result";
    els.uploadResult.innerHTML = `
      <div>
        <span class="status-pill ${esc(r.status)}">${esc(r.status)}</span>
        <strong>${r.parsed_lines}/${r.total_lines}</strong> lines parsed
      </div>
      <div class="ratio-bar">
        <span class="rp" style="width:${(r.parsed_lines / total) * 100}%"></span>
        <span class="rf" style="width:${(r.failed_lines / total) * 100}%"></span>
      </div>
      <div class="ratio-legend"><span>parsed ${r.parsed_lines}</span><span>skipped ${r.failed_lines}</span></div>
      ${r.errors?.length ? `<ul class="upload-errors">
        ${r.errors.map((e) => `<li>line ${esc(e.line)} — ${esc(e.reason)}</li>`).join("")}
      </ul>` : ""}`;
    els.uploadResult.classList.remove("hidden");
  }

  function renderUploadError(msg) {
    els.uploadResult.className = "upload-result";
    els.uploadResult.innerHTML = `<span class="status-pill failed">failed</span>${esc(msg)}`;
    els.uploadResult.classList.remove("hidden");
  }

  function setFile(f) {
    if (!f) return;
    const dt = new DataTransfer();
    dt.items.add(f);
    els.fileInput.files = dt.files;
    els.fileName.innerHTML = `<strong>${esc(f.name)}</strong> · ${(f.size / 1024).toFixed(1)} KB`;
    els.uploadBtn.disabled = false;
    els.uploadResult.classList.add("hidden");
  }

  els.fileInput.addEventListener("change", () => setFile(els.fileInput.files[0]));
  ["dragover", "dragenter"].forEach((ev) => els.dropZone.addEventListener(ev, (e) => {
    e.preventDefault(); els.dropZone.classList.add("dragover");
  }));
  ["dragleave", "drop"].forEach((ev) => els.dropZone.addEventListener(ev, () => els.dropZone.classList.remove("dragover")));
  els.dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
  });

  els.uploadForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = els.fileInput.files[0];
    if (!f) return;
    els.uploadBtn.disabled = true;
    els.uploadBtn.textContent = "Uploading…";
    try {
      const report = await window.Api.uploadLogs(f);
      renderUploadReport(report);
      refreshAll();
    } catch (err) {
      renderUploadError(err.message);
    } finally {
      els.uploadBtn.disabled = false;
      els.uploadBtn.textContent = "Upload";
    }
  });

  /* ---------------- filters / chips / pagination ---------------- */
  function applyFilters() { state.page = 1; writeQuery(); loadLogs(); }
  function resetFilters() {
    els.severity.value = ""; els.requestId.value = "";
    els.dateFrom.value = ""; els.dateTo.value = "";
    applyFilters();
  }
  els.applyBtn.addEventListener("click", applyFilters);
  els.resetBtn.addEventListener("click", resetFilters);
  els.clearFiltersLink.addEventListener("click", resetFilters);
  els.requestId.addEventListener("keydown", (e) => { if (e.key === "Enter") applyFilters(); });
  els.prevBtn.addEventListener("click", () => { state.page -= 1; loadLogs(); });
  els.nextBtn.addEventListener("click", () => { state.page += 1; loadLogs(); });
  els.logRetry.addEventListener("click", loadLogs);
  els.statsRetry.addEventListener("click", loadStats);

  document.querySelectorAll(".chip-try").forEach((chip) => chip.addEventListener("click", () => {
    resetInputs();
    if (chip.dataset.requestId) els.requestId.value = chip.dataset.requestId;
    if (chip.dataset.severity) els.severity.value = chip.dataset.severity;
    if (chip.dataset.last24) {
      els.dateFrom.value = toLocalInput(new Date(Date.now() - 24 * 3600e3).toISOString());
      els.dateTo.value = toLocalInput(new Date().toISOString());
    }
    applyFilters();
    if (chip.dataset.requestId) openTrace(chip.dataset.requestId);
  }));
  function resetInputs() {
    els.severity.value = ""; els.requestId.value = ""; els.dateFrom.value = ""; els.dateTo.value = "";
  }

  // ⌘K / Ctrl+K focuses the request-ID search (command-bar convention)
  document.addEventListener("keydown", (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      els.requestId.focus();
    }
  });

  /* ---------------- error streak alert strip ---------------- */
  async function loadStreaks() {
    try {
      const data = await window.Api.getStreaks(3);
      if (!data.streaks.length) { els.streakStrip.classList.add("hidden"); return; }
      els.streakChips.innerHTML = data.streaks.map((s) => `<button class="streak-chip"
          data-since="${esc(s.since)}"
          title="Since ${fmtAbs(s.since)} — click to view these errors">
          <strong>${esc(s.service)}</strong>&nbsp;×${s.streak} · ${esc(s.last_message || "…")}
        </button>`).join("");
      els.streakStrip.classList.remove("hidden");
    } catch (_) {
      els.streakStrip.classList.add("hidden");
    }
  }

  // Clicking a streak zooms the table onto the failing window: ERRORs since it began.
  els.streakChips.addEventListener("click", (e) => {
    const chip = e.target.closest(".streak-chip");
    if (!chip) return;
    resetInputs();
    els.severity.value = "ERROR";
    if (chip.dataset.since) els.dateFrom.value = toLocalInput(chip.dataset.since);
    applyFilters();
  });

  /* ---------------- shared refresh ---------------- */
  function refreshAll() {
    state.page = 1;
    loadHealth(); loadStats(); loadTimeline(); loadStreaks(); loadLogs();
  }

  /* ---------------- request trace drawer ---------------- */
  function showTrace(...visible) {
    [els.traceLoading, els.traceEmpty, els.traceError, els.traceSteps]
      .forEach((el) => el.classList.add("hidden"));
    visible.forEach((el) => el.classList.remove("hidden"));
  }

  async function openTrace(id) {
    state.traceId = id;
    writeQuery();
    els.traceIdBtn.textContent = id;
    els.traceIdBtn.title = "Copy request ID";
    els.traceMeta.textContent = "";
    els.traceOverlay.classList.remove("hidden");
    els.traceOverlay.setAttribute("aria-hidden", "false");
    showTrace(els.traceLoading);
    try {
      const data = await window.Api.getLogs({ requestId: id, limit: 100 });
      const steps = [...data.entries].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
      if (!steps.length) { showTrace(els.traceEmpty); return; }

      const services = new Set(steps.map((s) => s.service));
      const first = new Date(steps[0].timestamp).getTime();
      const last = new Date(steps[steps.length - 1].timestamp).getTime();
      els.traceMeta.textContent =
        `${steps.length} steps · ${services.size} services · span ${humanizeDuration(Math.max(0, last - first))}`;

      els.traceSteps.innerHTML = steps.map((s, i) => {
        const prev = i ? new Date(steps[i - 1].timestamp).getTime() : null;
        const gap = i ? new Date(s.timestamp).getTime() - prev : 0;
        return `<li class="step">
          <span class="step-dot c-${esc(s.severity)}"></span>
          <div>
            <span class="step-svc">${esc(s.service)}</span>
            ${gap >= 500 ? `<span class="step-gap">+${humanizeDuration(gap)}</span>` : ""}
            <span class="step-time">${fmtAbs(s.timestamp)}</span>
          </div>
          <div class="step-msg">${esc(s.message)}</div>
        </li>`;
      }).join("");
      showTrace(els.traceSteps);
    } catch (_) {
      showTrace(els.traceError);
    }
  }

  function closeTrace() {
    state.traceId = null;
    els.traceOverlay.classList.add("hidden");
    els.traceOverlay.setAttribute("aria-hidden", "true");
    writeQuery();
  }

  els.traceClose.addEventListener("click", closeTrace);
  els.traceOverlay.addEventListener("click", (e) => { if (e.target === els.traceOverlay) closeTrace(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && state.traceId) closeTrace(); });
  els.traceRetry.addEventListener("click", () => state.traceId && openTrace(state.traceId));
  els.traceIdBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(state.traceId);
      els.traceIdBtn.title = "Copied!";
      setTimeout(() => { els.traceIdBtn.title = "Copy request ID"; }, 1200);
    } catch (_) { /* clipboard unavailable (non-HTTPS) — ignore */ }
  });
  els.traceCopyLink.addEventListener("click", async () => {
    const url = `${location.origin}${location.pathname}?trace=${encodeURIComponent(state.traceId)}`;
    try {
      await navigator.clipboard.writeText(url);
      els.traceCopyLink.textContent = "Copied!";
      setTimeout(() => { els.traceCopyLink.textContent = "Copy link"; }, 1200);
    } catch (_) {
      window.prompt("Copy this link:", url);
    }
  });

  /* ---------------- init ---------------- */
  initTheme();
  const q = readQuery();
  loadHealth();
  loadStats();
  loadTimeline();
  loadStreaks();
  if (q.get("trace")) openTrace(q.get("trace"));
  loadLogs();
  setInterval(loadHealth, 60000);
})();
