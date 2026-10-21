/* ============================================================
 * mock.js — synthetic in-memory dataset for development.
 * Mirrors the shapes in docs/api-contract.md exactly.
 * Role 5 (test data) owns the real seed datasets; this mock
 * only exists so the frontend can be built before the backend.
 * Delete on Day 4 when USE_MOCK is flipped to false (or keep
 * for offline demos).
 * ============================================================ */
(function () {
  "use strict";

  // Deterministic pseudo-random generator so the demo looks the same every run.
  let seed = 42;
  function rand() {
    seed = (seed * 1664525 + 1013904223) % 4294967296;
    return seed / 4294967296;
  }
  function pick(arr) {
    return arr[Math.floor(rand() * arr.length)];
  }

  const SERVICES = [
    "auth-service",
    "payment-service",
    "api-gateway",
    "user-service",
    "inventory-service",
  ];

  // Recurring messages per severity — repetition is deliberate so the
  // "Top recurring errors" panel has meaningful groups.
  const MESSAGES = {
    DEBUG: ["Entering processOrder()", "SQL query executed in 12ms", "Cache hit for key user:42"],
    INFO: ["Request completed", "User login successful", "Health check passed", "Cache warmed"],
    WARN: ["Slow query detected (2.3s)", "Retrying upstream call (attempt 2)", "Deprecated API version used by client"],
    ERROR: [
      "Database connection timeout",
      "Failed to charge card: card declined",
      "Unhandled exception in request handler",
      "Upstream service returned 502",
    ],
    CRITICAL: ["Out of memory: worker killed", "Disk quota exceeded on volume /data"],
  };

  // Weighted severity distribution ≈ real production logs.
  const SEVERITY_POOL = [
    "DEBUG", "DEBUG",
    "INFO", "INFO", "INFO", "INFO",
    "WARN", "WARN",
    "ERROR", "ERROR",
    "CRITICAL",
  ];

  // Small pool of request IDs so tracing one ID shows a journey across services.
  const REQUEST_IDS = [];
  for (let i = 0; i < 40; i++) {
    REQUEST_IDS.push("req-" + Math.floor(rand() * 0xffffff).toString(16).padStart(6, "0"));
  }

  const entries = [];
  const now = Date.now();
  for (let id = 1; id <= 237; id++) {
    const severity = pick(SEVERITY_POOL);
    const ts = new Date(now - Math.floor(rand() * 72 * 3600 * 1000) - 1000);
    entries.push({
      id,
      timestamp: ts.toISOString(),
      severity,
      service: pick(SERVICES),
      request_id: rand() > 0.25 ? pick(REQUEST_IDS) : null,
      message: pick(MESSAGES[severity]),
    });
  }
  entries.sort((a, b) => b.timestamp.localeCompare(a.timestamp));

  window.MOCK_DB = {
    entries,
    nextId: 238,
    lastUpload: new Date(now - 3600 * 1000).toISOString(),
  };
})();
