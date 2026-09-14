const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
const html = fs.readFileSync(path.join(root, "web", "index.html"), "utf8");
const css = fs.readFileSync(path.join(root, "web", "styles.css"), "utf8");
const src = fs.readFileSync(path.join(root, "web", "app.js"), "utf8");

function assert(cond, label) {
  if (!cond) throw new Error(label);
}

const toolbarStart = html.indexOf('class="table-toolbar"');
const toolbarEnd = html.indexOf('class="table-shell"');
assert(toolbarStart >= 0 && toolbarEnd > toolbarStart, "table-toolbar missing");
const toolbar = html.slice(toolbarStart, toolbarEnd);
assert(toolbar.includes('id="btn-refresh-board"'), "refresh button in toolbar");
assert(toolbar.includes('id="flt-name"'), "name filter input in toolbar");
assert(
  toolbar.indexOf('id="btn-refresh-board"') < toolbar.indexOf('id="flt-name"'),
  "name input should sit on the same toolbar row after refresh"
);
assert(
  toolbar.indexOf('id="flt-name"') < toolbar.indexOf('id="mobile-sort"'),
  "name input should stay on the refresh row, before mobile sort chips"
);

assert(css.includes(".name-filter-input"), "name filter should have toolbar styles");
assert(
  /margin-left:\s*auto/.test(
    css.slice(css.indexOf(".name-filter-cluster"), css.indexOf(".name-filter-cluster") + 240)
  ) || /margin-left:\s*auto/.test(
    css.slice(css.indexOf(".name-filter-input"), css.indexOf(".name-filter-input") + 400)
  ),
  "name input should sit on the far right of the toolbar"
);

assert(src.includes('id="flt-name"') || src.includes("flt-name"), "app.js should read flt-name");
assert(src.includes("readNameFilter") || src.includes('flt-name'), "name filter reader missing");
assert(/flt-name[\s\S]{0,180}addEventListener\(\s*["']input["']/.test(src), "name filter should apply while typing");

assert(toolbar.includes('class="name-filter-wrap"'), "clear button wrap should sit around the name input");
assert(toolbar.includes('id="btn-name-filter-clear"'), "name filter should have an in-input clear button");
assert(
  toolbar.indexOf('id="flt-name"') < toolbar.indexOf('id="btn-name-filter-clear"'),
  "clear button should sit after the name input inside the wrap"
);
assert(
  /btn-name-filter-clear[\s\S]{0,200}class="[^"]*hidden/.test(toolbar) ||
    /id="btn-name-filter-clear"[^>]*class="[^"]*hidden/.test(toolbar),
  "clear button starts hidden when the input is empty"
);

assert(css.includes(".name-filter-wrap"), "name input wrap styles missing");
assert(css.includes(".name-filter-clear"), "clear button styles missing");
assert(css.includes("::-webkit-search-cancel-button"), "hide native search cancel to avoid two X buttons");
assert(src.includes("clearNameFilter"), "clearNameFilter missing");
assert(src.includes("syncNameFilterClear"), "syncNameFilterClear missing");
assert(
  /btn-name-filter-clear[\s\S]{0,220}addEventListener\(\s*["']click["']/.test(src) ||
    src.includes("nameFilterClearBtn?.addEventListener(\"click\""),
  "clear button should empty the name input on click"
);

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

const ember = { 名称: "EMBER", 市值: "10M", 持仓市值: "1M", 持仓人数: "3", 天数: "8.8" };
const pepe = { 名称: "pepe", 市值: "10M", 持仓市值: "1M", 持仓人数: "3", 天数: "8.8" };

assertEqual(matchesTokenFilters(ember, {}), true, "empty filters keep row");
assertEqual(matchesTokenFilters(ember, { name: "emb" }), true, "case-insensitive substring");
assertEqual(matchesTokenFilters(ember, { name: "EMBER" }), true, "exact name");
assertEqual(matchesTokenFilters(ember, { name: "pepe" }), false, "unrelated name dropped");
assertEqual(matchesTokenFilters(pepe, { name: "PE" }), true, "lowercase row matches uppercase query");
assertEqual(matchesTokenFilters(ember, { name: "  Emb  " }), true, "trimmed query");
assertEqual(matchesTokenFilters(ember, { name: "emb", daysMin: 9 }), false, "name AND other filters");
assert(hasAnyFilter({ name: "emb" }), "name-only counts as active filter");
assert(!hasAnyFilter({ name: "   " }), "blank name is not a filter");

console.log("ok");
