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

assert(src.includes("function holdMcapPctClass("), "holdMcapPctClass missing");
eval(src.slice(src.indexOf("function holdMcapPctClass("), src.indexOf("function matchesTokenFilters(")));
assertEqual(holdMcapPctClass(4.99), "", "below 5% keeps current color");
assertEqual(holdMcapPctClass(5), "hold-pct-mid", "5% is green band");
assertEqual(holdMcapPctClass(9.9), "hold-pct-mid", "under 10% is green");
assertEqual(holdMcapPctClass(10), "hold-pct-high", "10% is orange band");
assertEqual(holdMcapPctClass(15), "hold-pct-high", "15% is orange band");
assertEqual(holdMcapPctClass(15.1), "hold-pct-hot", "above 15% is red");
assertEqual(holdMcapPctClass(null), "", "missing percent keeps current color");

const renderFn = src.slice(src.indexOf("function renderTable("), src.indexOf("function chgClass("));
assert(renderFn.includes("holdMcapPctClass"), "table uses holdMcapPctClass");
assert(
  renderFn.includes('c === "持仓市值"') && renderFn.includes("holdMcapPctClass(parseHoldMcapPct(row))"),
  "table 持仓市值 color uses row percent"
);
const cardFn = src.slice(src.indexOf("function renderCards("), src.indexOf("function hideRowTip("));
assert(cardFn.includes("holdMcapPctClass"), "card 持仓市值 uses holdMcapPctClass");

assert(src.includes("function wrapHoldPctHtml("), "wrapHoldPctHtml missing");
eval(src.slice(src.indexOf("function wrapHoldPctHtml("), src.indexOf("function matchesTokenFilters(")));
eval(src.slice(src.indexOf("function escapeHtml("), src.indexOf("const TOKEN_CHART_COLORS")));
assertEqual(
  wrapHoldPctHtml("42.0M(16.2%)", 16.2),
  '<span class="hold-pct-hot">42.0M(16.2%)</span>',
  "tip 持仓市值 >15% is red"
);
assertEqual(
  wrapHoldPctHtml("29.0M(13.0%)", 13),
  '<span class="hold-pct-high">29.0M(13.0%)</span>',
  "tip 持仓市值 10-15% is orange"
);
assertEqual(
  wrapHoldPctHtml("3.3M(8.48%)", 8.48),
  '<span class="hold-pct-mid">3.3M(8.48%)</span>',
  "tip 持仓市值 5-10% is green"
);
assertEqual(wrapHoldPctHtml("2.0M(3.13%)", 3.13), "2.0M(3.13%)", "tip 持仓市值 <5% keeps current color");

const showFn = src.slice(src.indexOf("function showRowTip("), src.indexOf("function escapeHtml("));
assert(showFn.includes("wrapHoldPctHtml"), "tip header 持仓市值 uses wrapHoldPctHtml");
const paintFn = src.slice(src.indexOf("function paintTipClosedHolders("), src.indexOf("function showRowTip("));
assert(paintFn.includes("wrapHoldPctHtml"), "tip refresh 持仓市值 uses wrapHoldPctHtml");

const renderTipFn = src.slice(src.indexOf("function renderHolderTipRow("), src.indexOf("function holderIdentity("));
assert(renderTipFn.includes("holdMcapPctClass"), "tip holder 持仓市值 uses holdMcapPctClass");
assert(
  renderTipFn.includes('parseHoldMcapPct({ 持仓市值: parts.hold })') ||
    renderTipFn.includes('parseHoldMcapPct({持仓市值: parts.hold})'),
  "tip holder percent comes from hold text"
);

const css = fs.readFileSync(path.join(root, "web", "styles.css"), "utf8");
assert(css.includes(".hold-pct-mid"), "green band css");
assert(css.includes(".hold-pct-high"), "orange band css");
assert(css.includes(".hold-pct-hot"), "red band css");
assert(css.includes(".row-tip .hold-pct-mid"), "tip green band css");
assert(css.includes(".row-tip .hold-pct-high"), "tip orange band css");
assert(css.includes(".row-tip .hold-pct-hot"), "tip red band css");

console.log("ok");
