const fs = require("fs");
const path = require("path");
const src = fs.readFileSync(path.join(__dirname, "..", "web", "app.js"), "utf8");

function assert(cond, label) {
  if (!cond) throw new Error(label);
}

assert(src.includes("function drawTokenChart("), "drawTokenChart missing");
assert(src.includes("function loadTipTokenChart("), "loadTipTokenChart missing");
assert(src.includes("function refreshTipTokenChart("), "refreshTipTokenChart missing");
assert(src.includes("/api/fomo-top20/token-chart"), "must call token-chart API");
assert(src.includes("row-tip-chart"), "tip must include chart container");

const showFn = src.slice(src.indexOf("function showRowTip("), src.indexOf("function escapeHtml("));
const holdersAt = showFn.indexOf("holdersHtml");
const chartAt = showFn.indexOf("row-tip-chart");
assert(holdersAt >= 0 && chartAt > holdersAt, "layout B: chart HTML after holders");

assert(src.includes("function chartAxisTimeLabel("), "x-axis time label helper missing");
eval(src.slice(src.indexOf("function shortenTime("), src.indexOf("function createdAtMs(")));
const axisStart = src.indexOf("function chartAxisTimeLabel(");
const axisEnd = src.indexOf("function drawTokenChart(");
assert(axisStart >= 0 && axisEnd > axisStart, "chartAxisTimeLabel should sit before drawTokenChart");
eval(src.slice(axisStart, axisEnd));
assert(
  chartAxisTimeLabel("2026-09-11T11:00:00.000Z") === "09-11 19:00",
  "axis time should be Shanghai MM-DD HH:mm"
);

const drawFn = src.slice(src.indexOf("function drawTokenChart("), src.indexOf("function formatChartLegend("));
assert(drawFn.includes("chartAxisTimeLabel"), "drawTokenChart must label x-axis with time");
assert(drawFn.includes("fillText"), "drawTokenChart must paint axis time text");

assert(src.includes('TOKEN_CHART_COLORS'), "chart colors constant");
assert(src.includes("#c8f542") && src.includes("#6ec8ff") && src.includes("#ffb347"), "series colors");
assert(src.includes("#d48cff") && src.includes("#ff6b6b"), "holdMcap and pnl colors");

const refreshTipFn = src.slice(
  src.indexOf("function refreshTipTokenChart("),
  src.indexOf("function loadTipTokenChart(") > src.indexOf("function refreshTipTokenChart(")
    ? src.indexOf("async function copyText(")
    : src.indexOf("function loadTipTokenChart(")
);
assert(!/startRefresh(Summary)?\(/.test(refreshTipFn), "chart refresh must not start board refresh");
assert(!refreshTipFn.includes("setRefreshBusy("), "chart refresh must not toggle board busy");

const rememberFn = src.slice(
  src.indexOf("function rememberTokenHolders("),
  src.indexOf("function cloneTokenRow(")
);
assert(rememberFn.includes("tradeUpdatedAt"), "rememberTokenHolders must copy tradeUpdatedAt");

const cloneFn = src.slice(src.indexOf("function cloneTokenRow("), src.indexOf("function finalizeMergedRow("));
assert(cloneFn.includes("holders"), "cloneTokenRow must copy holders");

const pollFn = src.slice(
  src.indexOf("async function pollTipTokenChart("),
  src.indexOf("async function refreshTipTokenChart(")
);
assert(pollFn.includes("await fetchTipTokenChart"), "poll must await fetchTipTokenChart");
const fetchAt = pollFn.indexOf("await fetchTipTokenChart");
const genGuardAt = pollFn.indexOf("if (gen !== tipChartGen) return", fetchAt);
assert(fetchAt >= 0 && genGuardAt > fetchAt, "pollTipTokenChart must abort after fetch if gen changed");

console.log("ok");
