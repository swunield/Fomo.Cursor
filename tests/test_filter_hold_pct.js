const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const html = fs.readFileSync(path.join(root, "web", "index.html"), "utf8");
const src = fs.readFileSync(path.join(root, "web", "app.js"), "utf8");

function assert(cond, label) {
  if (!cond) throw new Error(label);
}

assert(html.includes("持仓市值比例区间"), "settings html should include 持仓市值比例区间");
assert(html.includes("flt-hold-pct-min"), "settings html should include flt-hold-pct-min");
assert(html.includes("flt-hold-pct-max"), "settings html should include flt-hold-pct-max");
assert(src.includes('key: "holdPctMin"'), "FILTER_FIELDS should include holdPctMin");
assert(src.includes('key: "holdPctMax"'), "FILTER_FIELDS should include holdPctMax");

const start = src.indexOf("function parseNumber(value)");
const end = src.indexOf("function compareSortValues(");
if (start < 0 || end < 0 || end <= start) {
  throw new Error("parseNumber/matchesTokenFilters block not found");
}
eval(src.slice(start, end));

function assertEqual(actual, expected, label) {
  if (actual !== expected) {
    throw new Error(`${label}: got ${JSON.stringify(actual)}, expected ${JSON.stringify(expected)}`);
  }
}

const row = { 市值: "100M", 持仓市值: "12.1M(12.1%)", 持仓人数: "3", 天数: "8.8" };
assertEqual(parseHoldMcapPct(row), 12.1, "parse percent from 持仓市值");
assertEqual(
  matchesTokenFilters(row, { holdPctMin: 10, holdPctMax: 15 }),
  true,
  "in range",
);
assertEqual(matchesTokenFilters(row, { holdPctMin: 13 }), false, "below min");
assertEqual(matchesTokenFilters(row, { holdPctMax: 12 }), false, "above max");
assertEqual(
  matchesTokenFilters(row, { holdPctMin: 12.1, holdPctMax: 12.1 }),
  true,
  "exact bound",
);

const computed = { 市值: "10M", 持仓市值: "1M", 持仓人数: "3", 天数: "1" };
assertEqual(parseHoldMcapPct(computed), 10, "compute percent from 持仓/市值");
assertEqual(matchesTokenFilters(computed, { holdPctMin: 8, holdPctMax: 12 }), true, "computed in range");
assertEqual(matchesTokenFilters(computed, { holdPctMax: 9 }), false, "computed above max");

console.log("ok");
