const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "..", "web", "app.js"), "utf8");
const start = src.indexOf("function createdAtMs(");
const end = src.indexOf("function normalizeBoard(");
if (start < 0 || end < 0 || end <= start) {
  throw new Error("createdAtMs/fmtAgeDays block not found in web/app.js");
}
eval(src.slice(start, end));

function assertEqual(actual, expected, label) {
  if (actual !== expected) {
    throw new Error(`${label}: got ${JSON.stringify(actual)}, expected ${JSON.stringify(expected)}`);
  }
}

const now = Date.parse("2026-09-12T08:15:50Z");
assertEqual(fmtAgeDays("", now), "", "empty");
assertEqual(fmtAgeDays("2026-09-01T16:15:50+00:00", now), "10.7", "utc iso");
assertEqual(fmtAgeDays("2026-09-02 00:15:50", now), "10.7", "shanghai display");

const colsMatch = src.match(/const COLUMNS = \[([\s\S]*?)\];/);
if (!colsMatch) throw new Error("COLUMNS not found");
const cols = [...colsMatch[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]);
if (cols[cols.indexOf("成交量") + 1] !== "天数") {
  throw new Error(`天数 should follow 成交量, got ${JSON.stringify(cols)}`);
}

console.log("ok");
