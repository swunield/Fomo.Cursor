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

assert(src.includes("const TOKEN_CHART_HIDDEN = new Set()"), "TOKEN_CHART_HIDDEN module set");
assert(src.includes("function toggleTokenChartKey("), "toggleTokenChartKey missing");
assert(
  /function toggleTokenChartKey\([^)]*\)[\s\S]*TOKEN_CHART_KEYS\.includes/.test(src),
  "toggleTokenChartKey must ignore unknown keys"
);

const legendFn = src.slice(
  src.indexOf("function formatChartLegend("),
  src.indexOf("function tipChartEls(")
);
assert(legendFn.includes("<button"), "legend items must be buttons");
assert(legendFn.includes('type="button"'), "legend buttons need type=button");
assert(legendFn.includes("data-key"), "legend buttons need data-key");
assert(legendFn.includes("row-tip-chart-legend-item"), "legend button class");
assert(legendFn.includes("is-hidden"), "hidden legend class");
assert(!legendFn.includes("<span style="), "legend must not keep static spans");

const css = fs.readFileSync(path.join(__dirname, "..", "web", "styles.css"), "utf8");
assert(css.includes(".row-tip-chart-legend-item"), "legend button css");
assert(css.includes(".row-tip-chart-legend-item.is-hidden"), "hidden legend css");
const hiddenBlock = css.slice(
  css.indexOf(".row-tip-chart-legend-item.is-hidden"),
  css.indexOf(".row-tip-chart-status")
);
assert(/opacity:\s*0\.4/.test(hiddenBlock), "hidden legend is faded");
assert(/text-decoration:\s*line-through/.test(hiddenBlock), "hidden legend is struck through");

assert(
  /for \(const key of TOKEN_CHART_KEYS\)[\s\S]*TOKEN_CHART_HIDDEN\.has\(key\)[\s\S]*continue/.test(drawFn),
  "drawTokenChart must skip hidden series"
);

assert(src.includes("function redrawTipChart("), "redrawTipChart missing");
const redrawFn = src.slice(
  src.indexOf("function redrawTipChart("),
  src.indexOf("function formatChartLegend(")
);
assert(redrawFn.includes("drawTokenChart"), "redrawTipChart must redraw canvas");
assert(redrawFn.includes("formatChartLegend"), "redrawTipChart must refresh legend");

const bindFn = src.slice(
  src.indexOf("function bindTipChart("),
  src.indexOf("async function copyText(")
);
assert(bindFn.includes('closest("[data-key]")') || bindFn.includes("closest('[data-key]')"), "legend click uses data-key");
assert(bindFn.includes("toggleTokenChartKey"), "legend click toggles key");
assert(bindFn.includes("redrawTipChart"), "legend click redraws");
assert(bindFn.includes("stopPropagation"), "legend click must not bubble");
assert(!/startRefresh(Summary)?\(/.test(bindFn), "legend click must not start board refresh");
assert(!bindFn.includes("setRefreshBusy("), "legend click must not toggle board busy");

console.log("ok");
