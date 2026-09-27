const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "..", "web", "app.js"), "utf8");

function assert(cond, label) {
  if (!cond) throw new Error(label);
}

function assertEqual(actual, expected, label) {
  if (actual !== expected) {
    throw new Error(`${label}: got ${JSON.stringify(actual)}, expected ${JSON.stringify(expected)}`);
  }
}

function assertDeep(actual, expected, label) {
  const a = JSON.stringify(actual);
  const b = JSON.stringify(expected);
  if (a !== b) throw new Error(`${label}: got ${a}, expected ${b}`);
}

assert(src.includes("function nextSortState("), "nextSortState missing");
assert(src.includes('key: "pct"'), "hold-mcap sort must track percent mode");

eval(
  src
    .slice(src.indexOf("const NUM_COLS = new Set(["), src.indexOf("const FILTER_STORAGE_KEY"))
    .replace("const NUM_COLS", "var NUM_COLS"),
);
eval(src.slice(src.indexOf("function parseNumber(value)"), src.indexOf("function fmtKm(")));
eval(src.slice(src.indexOf("function createdAtMs("), src.indexOf("function fmtAgeDays(")));
eval(src.slice(src.indexOf("function parseHoldMcapPct("), src.indexOf("function holdMcapPctClass(")));
eval(src.slice(src.indexOf("function isHoldPctSortCol("), src.indexOf("function compareSortValues(")));
eval(src.slice(src.indexOf("function nextSortState("), src.indexOf("function onHeaderClick(")));
eval(src.slice(src.indexOf("function compareSortValues("), src.indexOf("function sortRows(")));
eval(src.slice(src.indexOf("function sortRows("), src.indexOf("function sortIndicator(")));
eval(src.slice(src.indexOf("function sortIndicator("), src.indexOf("function nextSortState(")));

const HOLD_COLS = ["持仓市值", "最高持仓市值", "最低持仓市值"];
const none = { col: null, dir: null };
for (const HOLD of HOLD_COLS) {
  assertDeep(nextSortState(HOLD, none), { col: HOLD, dir: "desc", key: "value" }, `${HOLD} 1 市值降序`);
  assertDeep(
    nextSortState(HOLD, { col: HOLD, dir: "desc", key: "value" }),
    { col: HOLD, dir: "desc", key: "pct" },
    `${HOLD} 2 市值比例降序`,
  );
  assertDeep(
    nextSortState(HOLD, { col: HOLD, dir: "desc", key: "pct" }),
    { col: HOLD, dir: "asc", key: "value" },
    `${HOLD} 3 市值升序`,
  );
  assertDeep(
    nextSortState(HOLD, { col: HOLD, dir: "asc", key: "value" }),
    { col: HOLD, dir: "asc", key: "pct" },
    `${HOLD} 4 市值比例升序`,
  );
  assertDeep(
    nextSortState(HOLD, { col: HOLD, dir: "asc", key: "pct" }),
    { col: null, dir: null },
    `${HOLD} 5 无排序`,
  );
  assertDeep(
    nextSortState(HOLD, { col: "市值", dir: "desc" }),
    { col: HOLD, dir: "desc", key: "value" },
    `${HOLD} from other column starts at 市值降序`,
  );
}

const HOLD = "持仓市值";
const HI = "最高持仓市值";
const LO = "最低持仓市值";

const highPct = { 市值: "50M", 持仓市值: "8M(16%)" };
const highVal = { 市值: "100M", 持仓市值: "10M(10%)" };
assert(
  compareSortValues(highVal, highPct, HOLD, "desc", "value") < 0,
  "value desc: 10M before 8M",
);
assert(
  compareSortValues(highPct, highVal, HOLD, "desc", "pct") < 0,
  "pct desc: 16% before 10%",
);
assert(
  compareSortValues(highPct, highVal, HOLD, "asc", "value") < 0,
  "value asc: 8M before 10M",
);
assert(
  compareSortValues(highVal, highPct, HOLD, "asc", "pct") < 0,
  "pct asc: 10% before 16%",
);

const hiPct = { 市值: "50M", 最高持仓市值: "8M(16%)", 最低持仓市值: "1M(2%)" };
const hiVal = { 市值: "100M", 最高持仓市值: "10M(10%)", 最低持仓市值: "4M(4%)" };
assert(
  compareSortValues(hiVal, hiPct, HI, "desc", "value") < 0,
  "最高 value desc: 10M before 8M",
);
assert(
  compareSortValues(hiPct, hiVal, HI, "desc", "pct") < 0,
  "最高 pct desc: 16% before 10%",
);
assert(
  compareSortValues(hiPct, hiVal, LO, "desc", "pct") > 0,
  "最低 pct desc: 4% before 2%",
);
assert(
  compareSortValues(hiPct, hiVal, LO, "asc", "value") < 0,
  "最低 value asc: 1M before 4M",
);

let sortState = { col: HOLD, dir: "desc", key: "pct" };
const ordered = sortRows([highVal, highPct]).map((r) => r["持仓市值"]);
assertDeep(ordered, ["8M(16%)", "10M(10%)"], "sortRows pct desc");

sortState = { col: HI, dir: "desc", key: "pct" };
assertDeep(
  sortRows([hiVal, hiPct]).map((r) => r[HI]),
  ["8M(16%)", "10M(10%)"],
  "sortRows 最高 pct desc",
);
sortState = { col: LO, dir: "asc", key: "pct" };
assertDeep(
  sortRows([hiVal, hiPct]).map((r) => r[LO]),
  ["1M(2%)", "4M(4%)"],
  "sortRows 最低 pct asc",
);

for (const col of HOLD_COLS) {
  sortState = { col, dir: "desc", key: "pct" };
  assertEqual(sortIndicator(col), " %↓", `${col} pct desc indicator`);
  sortState = { col, dir: "asc", key: "pct" };
  assertEqual(sortIndicator(col), " %↑", `${col} pct asc indicator`);
  sortState = { col, dir: "desc", key: "value" };
  assertEqual(sortIndicator(col), " ↓", `${col} value desc indicator`);
  sortState = { col, dir: "asc", key: "value" };
  assertEqual(sortIndicator(col), " ↑", `${col} value asc indicator`);
}

const onClick = src.slice(src.indexOf("function onHeaderClick("), src.indexOf("function clearSort("));
assert(onClick.includes("nextSortState("), "header click uses nextSortState");
assert(src.includes("点击排序：市值↓ → 比例↓ → 市值↑ → 比例↑ → 无"), "hold-pct sort title");
assert(
  /最高持仓市值[\s\S]{0,400}点击排序：市值↓/.test(src) ||
    src.includes('HOLD_PCT_SORT_COLS') ||
    /c === "最高持仓市值"[\s\S]{0,80}c === "最低持仓市值"/.test(src) ||
    src.includes("isHoldPctSortCol("),
  "最高/最低 columns share hold-pct sort title",
);

console.log("ok");
