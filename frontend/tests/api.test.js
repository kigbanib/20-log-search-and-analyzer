/* ============================================================
 * api.test.js — frontend test suite for the API seam (js/api.js)
 * against the mock dataset. No framework needed — just Node:
 *
 *     node tests/api.test.js        (run from the frontend/ folder)
 *     node frontend/tests/api.test.js   (from the repo root)
 *
 * Covers the brief's required evidence:
 *   - happy path (filter, search, stats, upload)
 *   - major failure paths (oversized file, empty file, no matches)
 * After Day 4 integration, reuse these same expectations against
 * the real backend by pointing the suite at a staging URL.
 * ============================================================ */
"use strict";

const fs = require("fs");
const path = require("path");

// Load the browser files in a Node context (they attach to window).
global.window = {};
const root = path.join(__dirname, "..", "js");
eval(fs.readFileSync(path.join(root, "mock.js"), "utf8"));
eval(fs.readFileSync(path.join(root, "api.js"), "utf8"));
const Api = global.window.Api;

let pass = 0;
let fail = 0;
function check(name, cond) {
  cond ? pass++ : fail++;
  console.log((cond ? "PASS" : "FAIL") + "  " + name);
}

(async () => {
  console.log("Frontend API test suite (mock mode)\n");

  /* ---- health ---- */
  const h = await Api.getHealth();
  check("health: status ok and entries counted", h.status === "ok" && h.total_entries === 237);

  /* ---- pagination ---- */
  const p1 = await Api.getLogs({ page: 1, limit: 25 });
  check("pagination: page 1 returns 25 of 237", p1.entries.length === 25 && p1.total === 237);
  const p10 = await Api.getLogs({ page: 10, limit: 25 });
  check("pagination: last page returns remainder (12)", p10.entries.length === 12);
  check("pagination: pages do not overlap", p1.entries[0].id !== p10.entries[0].id);

  /* ---- severity filter ---- */
  const errs = await Api.getLogs({ severity: "error", limit: 500 }); // lowercase on purpose
  check("severity: case-insensitive filter returns only ERROR",
    errs.total > 0 && errs.entries.every((e) => e.severity === "ERROR"));

  /* ---- request-ID trace ---- */
  const rid = p1.entries.find((e) => e.request_id)?.request_id;
  const traced = await Api.getLogs({ requestId: rid, limit: 500 });
  check("request ID: trace returns only matching entries",
    traced.total > 0 && traced.entries.every((e) => e.request_id === rid));

  /* ---- failure path: no matches is empty, NOT an error ---- */
  const none = await Api.getLogs({ requestId: "req-does-not-exist" });
  check("no matches: returns empty list (not an error)", none.total === 0 && none.entries.length === 0);

  /* ---- date range ---- */
  const mid = Date.parse(p1.entries[Math.floor(p1.entries.length / 2)].timestamp);
  const ranged = await Api.getLogs({ from: new Date(mid).toISOString(), limit: 500 });
  check("date range: 'from' boundary respected",
    ranged.entries.every((e) => Date.parse(e.timestamp) >= mid));

  /* ---- recurring-error stats ---- */
  const stats = await Api.getErrorStats(10);
  check("stats: groups recurring errors, sorted by count",
    stats.errors.length >= 3 && stats.errors[0].count >= stats.errors[1].count);
  check("stats: first_seen <= last_seen, sample request IDs present",
    stats.errors[0].first_seen <= stats.errors[0].last_seen &&
    stats.errors[0].sample_request_ids.length > 0);

  /* ---- upload: happy path (partial report) ---- */
  const before = h.total_entries;
  const up = await Api.uploadLogs({ size: 1000, name: "demo.log" });
  check("upload: partial report is consistent (parsed + failed = total)",
    up.status === "partial" && up.parsed_lines + up.failed_lines === up.total_lines);
  check("upload: skipped lines reported with line numbers", up.errors.length > 0 && up.errors[0].line > 0);
  check("upload: parsed entries land in the dataset",
    (await Api.getHealth()).total_entries > before);

  /* ---- upload: MAJOR FAILURE PATHS ---- */
  try {
    await Api.uploadLogs({ size: 6 * 1024 * 1024 });
    check("failure path: oversized file (>5 MB) rejected", false);
  } catch (e) {
    check("failure path: oversized file (>5 MB) rejected", /5 MB/.test(e.message));
  }
  try {
    await Api.uploadLogs({ size: 0 });
    check("failure path: empty file rejected", false);
  } catch (e) {
    check("failure path: empty file rejected", /empty/.test(e.message));
  }

  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})().catch((e) => {
  console.error("SUITE ERROR:", e);
  process.exit(1);
});
