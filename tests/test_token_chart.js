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

eval(src.slice(src.indexOf("function tipChartMissingHint("), src.indexOf("function applyTipChartData(")));
assert(src.includes("function tipChartFetchedText("), "tipChartFetchedText missing");
assert(
  src.slice(src.indexOf("function tipChartFetchedText("), src.indexOf("function applyTipChartData(")).includes("shortenTime("),
  "fetched time next to refresh should use Shanghai time"
);
assertEqual(
  tipChartFetchedText({ lastFetchedAt: "2026-09-13T14:48:29.395507+00:00" }),
  "2026-09-13 22:48:29",
  "lastFetchedAt ISO UTC becomes Shanghai display beside refresh"
);
assertEqual(
  tipChartStatusText({ lastFetchedAt: "2026-09-13T14:48:29.395507+00:00" }, [{ t: "x" }]),
  "",
  "legend-below status should not repeat fetched time"
);
const applyFn = src.slice(src.indexOf("function applyTipChartData("), src.indexOf("async function fetchTipTokenChart("));
assert(applyFn.includes("els.fetched"), "applyTipChartData must paint fetched time");
assert(applyFn.includes("tipChartFetchedText"), "applyTipChartData must use tipChartFetchedText");

assert(src.includes("const TOKEN_CHART_HIDDEN = new Set()"), "TOKEN_CHART_HIDDEN module set");
assert(src.includes("function toggleTokenChartKey("), "toggleTokenChartKey missing");
assert(
  /function toggleTokenChartKey\([^)]*\)[\s\S]*TOKEN_CHART_KEYS\.includes/.test(src),
  "toggleTokenChartKey must ignore unknown keys"
);
assert(src.includes("function applyChartHidden("), "applyChartHidden missing");
assert(src.includes("function persistChartHidden("), "persistChartHidden missing");
const toggleFn = src.slice(src.indexOf("function toggleTokenChartKey("), src.indexOf("function chartAxisTimeLabel("));
assert(
  toggleFn.includes("persistChartHidden("),
  "toggling a legend key must persist hidden series to the server"
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

assert(src.includes("function chartPlotRect("), "chartPlotRect missing");
assert(src.includes("function chartXPositions("), "chartXPositions missing");
assert(src.includes("function nearestChartIndex("), "nearestChartIndex missing");
assert(src.includes("function clampChartCursor("), "clampChartCursor missing");
assert(src.includes("TOKEN_CHART_LONG_PRESS_MS"), "long-press duration constant missing");
assert(src.includes("TOKEN_CHART_SCRUB_PX"), "scrub pixel slop constant missing");

eval(src.slice(src.indexOf("function createdAtMs("), src.indexOf("function fmtAgeDays(")));
const helperStart = src.indexOf("function chartPlotRect(");
const helperEnd = src.indexOf("function drawTokenChart(");
assert(helperStart >= 0 && helperEnd > helperStart, "helpers should sit before drawTokenChart");
eval(src.slice(helperStart, helperEnd));

const sample = [
  { t: "2026-09-11T00:00:00.000Z", mcap: 1 },
  { t: "2026-09-11T12:00:00.000Z", mcap: 2 },
  { t: "2026-09-12T00:00:00.000Z", mcap: 3 },
];
assertEqual(nearestChartIndex(sample, 10, 640), 0, "left edge snaps to first point");
assertEqual(nearestChartIndex(sample, 630, 640), 2, "right edge snaps to last point");
assertEqual(nearestChartIndex([], 100, 640), null, "empty series has no cursor");
assertEqual(clampChartCursor(sample, 9), 2, "cursor clamps to last index");
assertEqual(clampChartCursor(sample, null), null, "null cursor stays null");

assert(/function formatChartLegend\(\s*series\s*,/.test(src), "formatChartLegend accepts cursor index");
assert(!legendFn.includes("row-tip-chart-cursor-time"), "selected time must not sit in the legend");
assert(showFn.includes("row-tip-chart-cursor-time"), "cursor time element missing in tip HTML");
assert(
  showFn.indexOf("持仓轨迹") < showFn.indexOf("row-tip-chart-cursor-time") &&
    showFn.indexOf("row-tip-chart-cursor-time") < showFn.indexOf("row-tip-chart-fetched"),
  "cursor time should sit after 持仓轨迹 and before fetched time"
);
assert(showFn.includes("row-tip-chart-fetched"), "fetched time should sit in chart head");
assert(
  showFn.indexOf("row-tip-chart-fetched") < showFn.indexOf("row-tip-chart-refresh") &&
    showFn.indexOf("row-tip-chart-refresh") < showFn.indexOf("row-tip-chart-canvas"),
  "fetched time should sit left of the refresh button"
);
assert(
  showFn.indexOf("row-tip-chart-fetched") < showFn.indexOf("row-tip-chart-status") &&
    showFn.indexOf("row-tip-chart-status") < showFn.indexOf("row-tip-chart-refresh") &&
    showFn.indexOf("row-tip-chart-refresh") < showFn.indexOf("row-tip-chart-canvas"),
  "progress/error status should sit left of the refresh button"
);
assert(
  showFn.indexOf("row-tip-chart-status") < showFn.indexOf("row-tip-chart-legend"),
  "status should not sit below the legend"
);
assertEqual(
  tipChartStatusText({ running: true, progress: { fetched: 3, total: 10 }, lastFetchedAt: "2026-09-13T14:48:29.395507+00:00" }, [{ t: "x" }]),
  "已拉 3/10",
  "running progress should still be a status string"
);
assertEqual(
  tipChartStatusText({ error: "刷新失败" }, [{ t: "x" }]),
  "刷新失败",
  "error should still be a status string"
);
assert(redrawFn.includes("cursorTime") || redrawFn.includes("row-tip-chart-cursor-time"), "redrawTipChart must update head time");
assert(drawFn.includes("setLineDash"), "drawTokenChart must draw dashed cursor");
assert(drawFn.includes("cursorIndex") || drawFn.includes("clampChartCursor"), "drawTokenChart reads cursor index");
assert(redrawFn.includes("_cursorIndex") || redrawFn.includes("cursor"), "redrawTipChart must pass cursor");

assert(bindFn.includes("pointerdown"), "canvas cursor uses pointerdown");
assert(bindFn.includes("pointerup") || bindFn.includes("pointercancel"), "canvas cursor uses pointerup");
assert(bindFn.includes("TOKEN_CHART_LONG_PRESS_MS") || bindFn.includes("400"), "long-press uses 400ms");
assert(bindFn.includes("nearestChartIndex"), "pointer maps x to nearest point");
assert(!/startRefresh(Summary)?\(/.test(bindFn), "chart pointer must not start board refresh");

const cssCursor = fs.readFileSync(path.join(__dirname, "..", "web", "styles.css"), "utf8");
assert(/touch-action:\s*none/.test(cssCursor.slice(
  cssCursor.indexOf(".row-tip-chart-canvas"),
  cssCursor.indexOf(".row-tip-chart-legend")
)), "canvas should disable native pan while scrubbing");
assert(cssCursor.includes(".row-tip-chart-cursor-time"), "selected time style missing");
assert(cssCursor.includes(".row-tip-chart-title"), "title+time cluster style missing");

console.log("ok");
