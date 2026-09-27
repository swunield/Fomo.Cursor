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
  "2026-09-13 22:48",
  "lastFetchedAt beside refresh keeps Shanghai time to the minute"
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
  "[3/10]",
  "running progress should be compact [fetched/total]"
);
assertEqual(
  tipChartStatusText({ error: "刷新失败" }, [{ t: "x" }]),
  "刷新失败",
  "error should still be a status string"
);
assertEqual(
  tipChartMissingHint({ warning: "请先刷新榜单", missingTradeIds: 4 }),
  "",
  "missing tradeId hint should stay hidden"
);
assertEqual(
  tipChartStatusText(
    { warning: "请先刷新榜单", stats: { missingTradeIds: 4 }, lastFetchedAt: "2026-09-13T14:48:29.395507+00:00" },
    [{ t: "x" }]
  ),
  "",
  "status must not show 请先刷新榜单 after a board refresh"
);
assert(
  !src.includes("请先刷新榜单"),
  "chart UI must not contain 请先刷新榜单"
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

assert(src.includes("function formatTipHolderCount("), "formatTipHolderCount missing");
assert(src.includes("function closedHolderTipLine("), "closedHolderTipLine missing");
assert(src.includes("function mergeClosedHolderLines("), "mergeClosedHolderLines missing");
assert(src.includes("function paintTipClosedHolders("), "paintTipClosedHolders missing");
assert(showFn.includes("formatTipHolderCount"), "tip title uses formatTipHolderCount");
assert(showFn.includes("row-tip-hold-head"), "tip holder head hook missing");
assert(applyFn.includes("paintTipClosedHolders"), "chart apply paints closed holders");
assert(src.includes("is-closed"), "closed holder row class");
assert(cssCursor.includes(".row-tip-holder-row.is-closed"), "closed holder css");

eval(src.slice(src.indexOf("function parseNumber(value)"), src.indexOf("function readFilterInputs(")));
eval(src.slice(src.indexOf("function shortenTime("), src.indexOf("function createdAtMs(")));
eval(src.slice(src.indexOf("function createdAtMs("), src.indexOf("function fmtAgeDays(")));
eval(src.slice(src.indexOf("function parseHolderTipParts("), src.indexOf("function renderHolderTipRow(")));
eval(src.slice(src.indexOf("function formatSummaryHolderWho("), src.indexOf("function relabelSummaryHolderLine(")));
eval(src.slice(src.indexOf("function formatTipHolderCount("), src.indexOf("function paintTipClosedHolders(")));

assertEqual(formatTipHolderCount(14, 2), "14(2)", "title is current(closed)");
assertEqual(formatTipHolderCount("14", 0), "14(0)", "zero closed still shown");

assert(src.includes("function formatTableHolderCount("), "formatTableHolderCount missing");
const renderStart = src.indexOf("function renderTable(");
const renderEnd = src.indexOf("function chgClass(");
assert(renderStart >= 0 && renderEnd > renderStart, "renderTable missing");
assert(
  src.slice(renderStart, renderEnd).includes("formatTableHolderCount"),
  "table 持仓人数 uses formatTableHolderCount"
);
const cardStart = src.indexOf("function renderCards(");
const cardEnd = src.indexOf("function holdersTableText(");
assert(cardStart >= 0 && cardEnd > cardStart, "renderCards missing");
assert(
  src.slice(cardStart, cardEnd).includes("formatTableHolderCount"),
  "card 持仓人数 uses formatTableHolderCount"
);
eval(src.slice(src.indexOf("function formatTableHolderCount("), src.indexOf("function formatTipHolderCount(")));
assertEqual(formatTableHolderCount(14, 2), "14/2", "table count is current/closed");
assertEqual(formatTableHolderCount("14", 0), "14/0", "table still shows zero closed");

const closedLine = closedHolderTipLine(
  {
    name: "Alice",
    handle: "alice",
    closedAt: "2026-09-13T04:00:00.000Z",
    holdingSince: "2026-09-11T11:00:00.000Z",
    pnlUsd: -10,
  },
  { 市值: "10M" }
);
const closedParts = parseHolderTipParts(closedLine);
assert(closedParts.who.includes("Alice"), "closed line keeps name");
assert(String(closedParts.hold).startsWith("0"), "closed hold value is 0");
assertEqual(closedParts.upd, "[20260913 12:00]", "last column is Shanghai close time");

const merged = mergeClosedHolderLines(
  ["1.Bob 10K(0.10%) +1K(+10.00%) [00:01:00] [20260913 12:00]"],
  [
    {
      name: "Alice",
      handle: "alice",
      closedAt: "2026-09-13T04:00:00.000Z",
      holdingSince: "2026-09-11T11:00:00.000Z",
      pnlUsd: -10,
    },
  ],
  { 市值: "10M" }
);
assertEqual(merged.open.length, 1, "keep current holders");
assertEqual(merged.closed.length, 1, "append closed holders");
assertEqual(merged.closedCount, 1, "closed count");
assert(merged.lines[0].includes("Bob"), "current holders stay on top");
assert(merged.lines[merged.lines.length - 1].includes("Alice"), "closed holders go to bottom");

const skipped = mergeClosedHolderLines(
  ["1.Alice 10K(0.10%) +1K(+10.00%) [00:01:00] [20260913 12:00]"],
  [{ name: "Alice", handle: "alice", closedAt: "2026-09-13T04:00:00.000Z", pnlUsd: -10 }],
  { 市值: "10M" }
);
assertEqual(skipped.closed.length, 0, "do not duplicate a still-listed holder as closed");

console.log("ok");
