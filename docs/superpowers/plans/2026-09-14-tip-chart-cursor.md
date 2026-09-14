# Tips 图表时间轴虚线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Canvas 点击/长按钉垂直虚线，图例显示该时间点数据；再点取消，长按或滑动可拖动。

**Architecture:** 纯前端。抽出与绘制共用的 x 映射和最近点下标；cursor 存在 `box._cursorIndex`；pointer 事件区分单击切换与长按/滑动跟随。

**Tech Stack:** vanilla JS、canvas 2D、`node tests/test_token_chart.js`

## Global Constraints

- 不改后端 / HTTP
- 不对序列点插值
- 不触发榜单刷新（`startRefresh` / `setRefreshBusy`）
- 用户未要求时不 git commit

---

### Task 1: 最近点与图例/虚线绘制

**Files:**
- Modify: `web/app.js`（`chartAxisTimeLabel` 与 `drawTokenChart` 之间加 helpers；改 `drawTokenChart` / `formatChartLegend` / `redrawTipChart` / `applyTipChartData`）
- Modify: `web/styles.css`（canvas `touch-action`、时间标签）
- Modify: `web/index.html`（静态资源 `?v=`）
- Test: `tests/test_token_chart.js`

**Interfaces:**
- Produces: `chartPlotRect(width, height)`, `chartXPositions(series, width)`, `nearestChartIndex(series, x, width)`, `clampChartCursor(series, index)`, `drawTokenChart(canvas, series, cursorIndex)`, `formatChartLegend(series, cursorIndex)`

- [ ] Write failing tests in `tests/test_token_chart.js`
- [ ] Run `node tests/test_token_chart.js` — expect FAIL
- [ ] Implement helpers + draw dashed line + legend cursor
- [ ] Run tests — expect PASS

### Task 2: Canvas 指针手势

**Files:**
- Modify: `web/app.js` `bindTipChart`
- Test: `tests/test_token_chart.js`

**Interfaces:**
- Consumes: Task 1 helpers
- Produces: `bindTipChartCursor(els)`；`TOKEN_CHART_LONG_PRESS_MS = 400`；`TOKEN_CHART_SCRUB_PX = 8`

- [ ] Extend failing tests for pointerdown/up/move and no board refresh
- [ ] Implement bindTipChartCursor
- [ ] Run `node tests/test_token_chart.js` — expect PASS
- [ ] Browser: 单击钉线、再点取消、长按拖动
