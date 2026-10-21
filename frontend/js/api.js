/* ============================================================
 * api.js — THE integration seam.
 *
 * Every backend call in the UI goes through this file. Mock mode
 * runs entirely in the browser against window.MOCK_DB; real mode
 * talks to the FastAPI backend using the agreed contract
 * (docs/api-contract.md).
 *
 * DAY 4 INTEGRATION = change USE_MOCK to false. Nothing else in
 * the UI should need to change. If it does, the contract drifted
 * — flag it to the team.
 * ============================================================ */
(function () {
  "use strict";

  const USE_MOCK = typeof window !== 'undefined' && window.USE_MOCK !== undefined ? window.USE_MOCK : false; // integration: false (was true in dev)
  const API_BASE = "";              // "" = same origin (FastAPI serves this UI)
  const PAGE_SIZE = 25;
  const MAX_UPLOAD_BYTES = 5 * 1024 * 1024; // matches backend MAX_UPLOAD_MB=5

  const delay = (ms) => new Promise((r) => setTimeout(r, ms));
  const clone = (o) => JSON.parse(JSON.stringify(o));

  /* ---------------- real-mode transport ---------------- */
  async function http(path, options = {}) {
    const res = await fetch(API_BASE + path, options);
    let data = {};
    try {
      data = await res.json();
    } catch (_) {
      /* non-JSON body — handled below */
    }
    if (!res.ok) {
      // FastAPI error shape: { "detail": "..." }
      throw new Error(data.detail || `Request failed (HTTP ${res.status})`);
    }
    return data;
  }

  /* ---------------- mock implementations ---------------- */
  const mock = {
    async getHealth() {
      await delay(250);
      return clone({
        status: "ok",
        db: "ok",
        total_entries: window.MOCK_DB.entries.length,
        last_upload: window.MOCK_DB.lastUpload,
      });
    },

    async uploadLogs(file) {
      await delay(900); // make the loading state visible
      if (file.size > MAX_UPLOAD_BYTES) {
        throw new Error("File exceeds the 5 MB upload limit.");
      }
      if (file.size === 0) {
        throw new Error("The selected file is empty.");
      }
      // Simulate a 'partial' upload: most lines parsed, a few reported.
      const report = {
        upload_id: Math.floor(Math.random() * 1000),
        status: "partial",
        total_lines: 500,
        parsed_lines: 487,
        failed_lines: 13,
        errors: [
          { line: 12, reason: "unknown severity 'FATAL'" },
          { line: 88, reason: "missing timestamp" },
          { line: 201, reason: "line is not valid JSON" },
        ],
      };
      // Pretend the parsed lines landed in the DB so the table updates.
      const db = window.MOCK_DB;
      const t = Date.now();
      const fresh = [];
      for (let i = 0; i < 8; i++) {
        fresh.push({
          id: db.nextId++,
          timestamp: new Date(t - i * 60 * 1000).toISOString(),
          severity: i % 3 === 0 ? "ERROR" : "INFO",
          service: "auth-service",
          request_id: i % 2 === 0 ? "req-upload01" : null,
          message: i % 3 === 0 ? "Database connection timeout" : "Request completed",
        });
      }
      db.entries = fresh.concat(db.entries);
      db.lastUpload = new Date().toISOString();
      return report;
    },

    async getLogs({ severity = "", requestId = "", from = "", to = "", page = 1, limit = PAGE_SIZE } = {}) {
      await delay(400);
      let rows = window.MOCK_DB.entries.slice();
      if (severity) {
        const want = severity.toUpperCase();
        rows = rows.filter((e) => e.severity === want);
      }
      if (requestId) {
        rows = rows.filter((e) => e.request_id === requestId);
      }
      if (from) {
        const fromMs = new Date(from).getTime();
        if (!Number.isNaN(fromMs)) rows = rows.filter((e) => Date.parse(e.timestamp) >= fromMs);
      }
      if (to) {
        const toMs = new Date(to).getTime();
        if (!Number.isNaN(toMs)) rows = rows.filter((e) => Date.parse(e.timestamp) <= toMs);
      }
      const total = rows.length;
      const start = (page - 1) * limit;
      return clone({
        total,
        page,
        limit,
        entries: rows.slice(start, start + limit),
      });
    },

    async getErrorStats(top = 10) {
      await delay(400);
      const groups = new Map();
      for (const e of window.MOCK_DB.entries) {
        if (e.severity !== "ERROR" && e.severity !== "CRITICAL") continue;
        let g = groups.get(e.message);
        if (!g) {
          g = {
            message: e.message,
            severity: e.severity,
            count: 0,
            first_seen: e.timestamp,
            last_seen: e.timestamp,
            sample_request_ids: [],
          };
          groups.set(e.message, g);
        }
        g.count += 1;
        if (e.timestamp < g.first_seen) g.first_seen = e.timestamp;
        if (e.timestamp > g.last_seen) g.last_seen = e.timestamp;
        if (e.request_id && !g.sample_request_ids.includes(e.request_id) && g.sample_request_ids.length < 3) {
          g.sample_request_ids.push(e.request_id);
        }
      }
      const errors = [...groups.values()].sort((a, b) => b.count - a.count).slice(0, top);
      return clone({ errors });
    },
  };

  /* ---------------- public API (same shape either mode) ---------------- */
  window.Api = {
    PAGE_SIZE,
    MAX_UPLOAD_BYTES,
    USE_MOCK,

    getHealth() {
      return USE_MOCK ? mock.getHealth() : http("/api/health");
    },

    uploadLogs(file) {
      if (USE_MOCK) return mock.uploadLogs(file);
      const form = new FormData();
      form.append("file", file); // field name MUST be "file" per contract
      return http("/api/logs/upload", { method: "POST", body: form });
    },

    getLogs(params) {
      if (USE_MOCK) return mock.getLogs(params);
      const qs = new URLSearchParams();
      if (params.severity) qs.set("severity", params.severity);
      if (params.requestId) qs.set("request_id", params.requestId);
      if (params.from) qs.set("from", params.from);
      if (params.to) qs.set("to", params.to);
      qs.set("page", params.page || 1);
      qs.set("limit", params.limit || PAGE_SIZE);
      return http("/api/logs?" + qs.toString());
    },

    getErrorStats(top = 10) {
      return USE_MOCK ? mock.getErrorStats(top) : http("/api/stats/errors?top=" + top);
    },
  };
})();
