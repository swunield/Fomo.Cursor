const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "..", "web", "app.js"), "utf8");
const html = fs.readFileSync(path.join(__dirname, "..", "web", "index.html"), "utf8");

function assert(cond, label) {
  if (!cond) throw new Error(label);
}

assert(html.includes('data-board="sum"'), "sidebar should have 汇总 board");
assert(html.includes(">汇总<"), "sidebar label should be 汇总");
assert(
  html.indexOf('data-board="sum"') < html.indexOf('data-board="all"'),
  "汇总 should be the first sidebar board"
);

assert(src.includes('board === "sum"') && src.includes('return "sum"'), "normalizeBoard should keep sum");
assert(src.includes('return "汇总"') || src.includes("`汇总`"), "boardLabel should name 汇总");
assert(src.includes("mergeSummaryPayloads("), "should merge three board payloads");
const refreshFn = src.slice(
  src.indexOf("async function startRefreshSummary"),
  src.indexOf("async function selectSummaryBoard")
);
assert(refreshFn.includes("startRefreshSummary"), "startRefreshSummary missing");
assert(
  /board:\s*["']sum["']/.test(refreshFn),
  "汇总刷新应一次提交 board=sum，避免同一玩家拉三次持仓"
);
assert(
  !refreshFn.includes("for (const board of SOURCE_BOARDS)"),
  "汇总刷新不应再依次请求三榜 refresh"
);
assert(src.includes("async function unlockRefreshIfIdle"), "must gate refresh unlock on job status");
const summarySelectFn = src.slice(
  src.indexOf("async function selectSummaryBoard"),
  src.indexOf("async function pollUntilDone")
);
assert(summarySelectFn.includes("unlockRefreshIfIdle"), "selecting 汇总 must not enable refresh while job runs");
assert(
  !summarySelectFn.includes("setRefreshBusy(false)"),
  "selectSummaryBoard must not blindly re-enable refresh"
);
const pollFn = src.slice(
  src.indexOf("async function pollUntilDone"),
  src.indexOf("function ensurePolling")
);
const busyFalseAt = pollFn.indexOf("setRefreshBusy(false)");
const loadSumAt = pollFn.indexOf("loadSummaryFromCache");
assert(loadSumAt >= 0, "pollUntilDone should load summary caches");
assert(
  busyFalseAt < 0 || (loadSumAt >= 0 && busyFalseAt > loadSumAt),
  "keep refresh disabled until summary caches finish loading"
);

const boardSettings = { allLimit: 20, dayLimit: 50, h24Limit: 50 };
const bStart = src.indexOf("const SOURCE_BOARDS");
const bEnd = src.indexOf("function applySettingsToUi(");
assert(bStart >= 0 && bEnd > bStart, "SOURCE_BOARDS/boardLabel block missing");
eval(src.slice(bStart, bEnd));

const nStart = src.indexOf("function parseNumber(value)");
const nEnd = src.indexOf("function readFilterInputs(");
assert(nStart >= 0 && nEnd > nStart, "parseNumber/fmtKm block missing");
eval(src.slice(nStart, nEnd));

const hStart = src.indexOf("function holderTipLines(");
const hEnd = src.indexOf("function showRowTip(");
assert(hStart >= 0 && hEnd > hStart, "holder/merge block missing");
eval(src.slice(hStart, hEnd));

function assertEqual(actual, expected, label) {
  if (actual !== expected) {
    throw new Error(`${label}: got ${JSON.stringify(actual)}, expected ${JSON.stringify(expected)}`);
  }
}

assertEqual(normalizeBoard("sum"), "sum", "normalize sum");
assertEqual(boardLabel("sum"), "汇总", "label");
assert(typeof cachePayloadUsable === "function", "cachePayloadUsable missing");
assert(cachePayloadUsable({ ok: true, rows: [], traderRanks: [{ rank: 13, name: "x" }] }), "empty rows still usable with traderRanks");
assert(!cachePayloadUsable({ ok: true, rows: [], traderRanks: [] }), "empty cache not usable");

const a = {
  board: "all",
  generatedAt: "2026-09-13T01:00:00Z",
  rows: [
    {
      名称: "AAA",
      市值: "10.0M",
      合约地址: "So1AAA",
      持仓明细: ["1.Alice 1.0M(10.0%) +100K(+10%)", "2.Bob 500K(5.00%) -20K(-4%)"],
      所有持仓人: "1.Alice 1.0M(10.0%) +100K(+10%)\n2.Bob 500K(5.00%) -20K(-4%)",
    },
  ],
};
const b = {
  board: "7d",
  generatedAt: "2026-09-13T02:00:00Z",
  rows: [
    {
      名称: "AAA",
      市值: "10.0M",
      合约地址: "so1aaa",
      持仓明细: ["8.Alice 1.2M(12.0%) +200K(+20%)", "3.Cara 300K(3.00%) +10K(+3%)"],
      所有持仓人: "8.Alice 1.2M(12.0%) +200K(+20%)\n3.Cara 300K(3.00%) +10K(+3%)",
    },
    {
      名称: "BBB",
      市值: "2.0M",
      合约地址: "So1BBB",
      持仓明细: ["4.Dan 200K(10.0%) +5K(+2%)"],
      所有持仓人: "4.Dan 200K(10.0%) +5K(+2%)",
    },
  ],
};

const merged = mergeSummaryPayloads([a, b]);
assertEqual(merged.board, "sum", "merged board");
assertEqual(merged.rows.length, 2, "two tokens");
const aaa = merged.rows.find((r) => r["合约地址"] === "So1AAA");
assert(aaa, "AAA row");
assertEqual(Number(aaa["持仓人数"]), 3, "Alice+Bob+Cara");
assert(String(aaa["所有持仓人"]).includes("Cara"), "union includes Cara");
assert(String(aaa["所有持仓人"]).includes("Alice"), "union includes Alice");
assert(!String(aaa["所有持仓人"]).includes("1.Alice 1.0M"), "Alice uses newer 7d snapshot");
assert(String(aaa["所有持仓人"]).includes("1.2M"), "Alice from newer 7d");
assert(String(aaa["所有持仓人"]).includes("1.8.0.Alice"), "Alice ranks all=1,7d=8,24h=0");
assert(String(aaa["所有持仓人"]).includes("2.0.0.Bob"), "Bob only on all-time");
assert(String(aaa["所有持仓人"]).includes("0.3.0.Cara"), "Cara only on 7d");
assertEqual(aaa["最高持仓人"], "1.8.0.Alice", "highest holder uses triple rank");
const bbb = merged.rows.find((r) => r["合约地址"] === "So1BBB");
assert(bbb, "BBB row");
assertEqual(Number(bbb["持仓人数"]), 1, "BBB one holder");
assert(String(bbb["所有持仓人"]).includes("0.4.0.Dan"), "Dan only on 7d");
assertEqual(merged.rows[0]["合约地址"], aaa["合约地址"], "sorted by holding mcap");

const h24 = {
  board: "24h",
  generatedAt: "2026-09-13T02:30:00Z",
  rows: [
    {
      名称: "AAA",
      市值: "10.0M",
      合约地址: "So1AAA",
      持仓明细: ["12.Alice 1.1M(11.0%) +150K(+15%)"],
    },
  ],
};
const withDay = mergeSummaryPayloads([a, b, h24]);
const withDayAaa = withDay.rows.find((r) => r["合约地址"] === "So1AAA");
assert(String(withDayAaa["所有持仓人"]).includes("1.8.12.Alice"), "Alice ranks include 1-day board");
assert(String(withDayAaa["所有持仓人"]).includes("1.1M"), "Alice holding from newest 24h snapshot");
assertEqual(withDayAaa["最高持仓人"], "1.8.12.Alice", "highest who uses three ranks");

const olderBigger = {
  board: "7d",
  generatedAt: "2026-09-13T02:00:00Z",
  rows: [
    {
      名称: "AAA",
      市值: "10.0M",
      合约地址: "So1AAA",
      持仓明细: ["8.Alice 1.2M(12.0%) +200K(+20%)", "3.Cara 300K(3.00%) +10K(+3%)"],
    },
    {
      名称: "CCC",
      市值: "1.0M",
      合约地址: "So1CCC",
      持仓明细: ["8.Alice 400K(40.0%) +10K(+3%)"],
    },
  ],
};
const newerSmaller = {
  board: "all",
  generatedAt: "2026-09-13T03:00:00Z",
  rows: [
    {
      名称: "AAA",
      市值: "10.0M",
      合约地址: "So1AAA",
      持仓明细: ["1.Alice 800K(8.00%) +50K(+6%)", "2.Bob 500K(5.00%) -20K(-4%)"],
    },
  ],
};
const newestWins = mergeSummaryPayloads([olderBigger, newerSmaller]);
const newestAaa = newestWins.rows.find((r) => String(r["合约地址"]).toLowerCase() === "so1aaa");
assert(newestAaa, "newest AAA");
assert(String(newestAaa["所有持仓人"]).includes("800K"), "Alice uses newest query even if smaller");
assert(!String(newestAaa["所有持仓人"]).includes("1.2M"), "stale larger Alice holding dropped");
assert(String(newestAaa["所有持仓人"]).includes("Cara"), "Cara only on older board is kept");
assert(String(newestAaa["所有持仓人"]).includes("1.8.0.Alice"), "Alice keeps ranks from both boards");
assert(String(newestAaa["所有持仓人"]).includes("0.3.0.Cara"), "Cara rank from 7d only");
assert(
  !newestWins.rows.some((r) => String(r["合约地址"]).toLowerCase() === "so1ccc"),
  "Alice sold CCC after newer query, drop stale token"
);

const allTradersOnly = {
  board: "all",
  generatedAt: "2026-09-13T01:00:00Z",
  traderRanks: [{ rank: 13, name: "point farm capital", handle: "pointfarmcap" }],
  rows: [],
};
const dayHoldings = {
  board: "7d",
  generatedAt: "2026-09-13T02:00:00Z",
  rows: [
    {
      名称: "AAA",
      市值: "10.0M",
      合约地址: "So1STONK",
      持仓明细: ["1.point farm capital 9.4M(4.17%) +8.9M(+1642%)"],
    },
  ],
};
const ranked = mergeSummaryPayloads([allTradersOnly, dayHoldings]);
const stonk = ranked.rows.find((r) => r["合约地址"] === "So1STONK");
assert(stonk, "STONK row");
assert(
  String(stonk["所有持仓人"]).includes("13.1.0.point farm capital"),
  "总榜 rank comes from trader list even without 总榜 holdings"
);

console.log("ok");
