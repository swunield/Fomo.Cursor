const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const html = fs.readFileSync(path.join(root, "web", "index.html"), "utf8");
const src = fs.readFileSync(path.join(root, "web", "app.js"), "utf8");

function assert(cond, label) {
  if (!cond) throw new Error(label);
}

assert(html.includes("天数区间"), "settings html should include 天数区间");
assert(html.includes("flt-days-min"), "settings html should include flt-days-min");
assert(html.includes("flt-days-max"), "settings html should include flt-days-max");
assert(src.includes('key: "daysMin"'), "FILTER_FIELDS should include daysMin");
assert(src.includes('key: "daysMax"'), "FILTER_FIELDS should include daysMax");

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

const row = { 天数: "8.8", 市值: "10M", 持仓市值: "1M", 持仓人数: "3" };
assertEqual(
  matchesTokenFilters(row, { daysMin: 5, daysMax: 10 }),
  true,
  "in range",
);
assertEqual(
  matchesTokenFilters(row, { daysMin: 9 }),
  false,
  "below min",
);
assertEqual(
  matchesTokenFilters(row, { daysMax: 8 }),
  false,
  "above max",
);
assertEqual(
  matchesTokenFilters(row, { daysMin: 8.8, daysMax: 8.8 }),
  true,
  "exact bound",
);

console.log("ok");
