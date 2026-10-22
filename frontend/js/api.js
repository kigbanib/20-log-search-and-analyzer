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
  // Pristine dataset snapshot for mock-mode "Reset" (mock.js loads before this).
  const baseline =
    typeof window !== "undefined" && window.MOCK_DB ? window.MOCK_DB.entries.slice() : [];

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

    async getTimeline(bucket = "hour") {
      await delay(300);
      const SEVS = ["DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"];
      const maxBuckets = bucket === "hour" ? 72 : 60;
      const counts = new Map();
      for (const e of window.MOCK_DB.entries) {
        const d = new Date(e.timestamp);
        const key = bucket === "hour"
          ? d.toISOString().slice(0, 13) + ":00:00Z"
          : d.toISOString().slice(0, 10);
        if (!counts.has(key)) counts.set(key, Object.fromEntries(SEVS.map((s) => [s, 0])));
        counts.get(key)[e.severity] += 1;
      }
      const keys = [...counts.keys()].sort().slice(-maxBuckets);
      const step = bucket === "hour" ? 3600e3 : 86400e3;
      const buckets = [];
      if (keys.length) {
        // zero-fill between first and last bucket
        const parseKey = (k) => new Date(bucket === "hour" ? k : k + "T00:00:00Z").getTime();
        let t = parseKey(keys[0]);
        const end = parseKey(keys[keys.length - 1]);
        while (t <= end) {
          const d = new Date(t);
          const key = bucket === "hour" ? d.toISOString().slice(0, 13) + ":00:00Z" : d.toISOString().slice(0, 10);
          const existing = counts.get(key) || Object.fromEntries(SEVS.map((s) => [s, 0]));
          buckets.push({ start: key, ...existing });
          t += step;
        }
      }
      return clone({ bucket, buckets });
    },

    async demoScenario(name = "incident") {
      await delay(600);
      const db = window.MOCK_DB;
      const hero = "req-inc7001";
      const now = Date.now();
      const story = [
        [10, "INFO", "api-gateway", "POST /api/checkout received", hero],
        [9, "WARN", "payment-service", "Retrying upstream call (attempt 2)", hero],
        [8, "ERROR", "auth-service", "Database connection timeout", hero],
        [7, "ERROR", "payment-service", "Database connection timeout", hero],
        [6, "ERROR", "api-gateway", "Upstream service returned 502", hero],
        [5, "ERROR", "payment-service", "Database connection timeout", "req-b-235"],
        [4, "ERROR", "payment-service", "Database connection timeout", "req-b-239"],
        [3, "ERROR", "payment-service", "Database connection timeout", "req-b-243"],
        [2, "ERROR", "payment-service", "Database connection timeout", "req-b-247"],
        [1, "ERROR", "payment-service", "Circuit breaker OPEN for db-primary", "req-b-251"],
      ];
      for (const [m, sev, svc, msg, rid] of story) {
        db.entries.unshift({
          id: db.nextId++,
          timestamp: new Date(now - m * 60e3).toISOString(),
          severity: sev, service: svc, request_id: rid, message: msg,
        });
      }
      db.lastUpload = new Date().toISOString();
      return clone({ scenario: name, inserted: story.length, hero_request_id: hero, story: "deploy → cascading timeouts" });
    },

    async demoReset() {
      await delay(500);
      window.MOCK_DB.entries = baseline.slice();
      window.MOCK_DB.lastUpload = new Date().toISOString();
      return clone({ reset: true, seeded: window.MOCK_DB.entries.length });
    },

    async getStreaks(min = 3) {
      await delay(250);
      const BAD = new Set(["ERROR", "CRITICAL"]);
      const byService = new Map();
      // MOCK_DB.entries are newest-first — same tail-scan as the real backend.
      for (const e of window.MOCK_DB.entries) {
        let cur = byService.get(e.service);
        if (!cur) {
          cur = {
            service: e.service, streak: 0, since: null, last_seen: null,
            last_message: null, sample_request_ids: [], _open: true,
          };
          byService.set(e.service, cur);
        }
        if (!cur._open) continue;
        if (BAD.has(e.severity)) {
          if (cur.streak === 0) { cur.last_seen = e.timestamp; cur.last_message = e.message; }
          cur.streak += 1;
          cur.since = e.timestamp;
          if (e.request_id && cur.sample_request_ids.length < 3 && !cur.sample_request_ids.includes(e.request_id)) {
            cur.sample_request_ids.push(e.request_id);
          }
        } else {
          cur._open = false;
        }
      }
      const streaks = [...byService.values()]
        .filter((s) => s.streak >= min)
        .sort((a, b) => b.streak - a.streak || a.service.localeCompare(b.service))
        .map(({ _open, ...s }) => s);
      return clone({ min_streak: min, streaks });
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

    getTimeline(bucket = "hour") {
      return USE_MOCK ? mock.getTimeline(bucket) : http("/api/stats/timeline?bucket=" + bucket);
    },

    demoScenario(name = "incident") {
      return USE_MOCK
        ? mock.demoScenario(name)
        : http(`/api/demo/scenario/${name}`, { method: "POST" });
    },

    demoReset() {
      return USE_MOCK ? mock.demoReset() : http("/api/demo/reset", { method: "POST" });
    },

    getStreaks(min = 3) {
      return USE_MOCK ? mock.getStreaks(min) : http("/api/stats/streaks?min=" + min);
    },
  };
})();
