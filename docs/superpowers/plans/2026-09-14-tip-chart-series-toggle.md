# Tips 图表曲线显示/隐藏 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 点击 Tip 持仓轨迹图图例，单独显示或隐藏市值、人数、数量、持仓市值、盈亏五条曲线。

**Architecture:** 前端模块级 `Set` 记录隐藏的 series key。`drawTokenChart` 跳过 Set 中的 key；`formatChartLegend` 把图例改成带 `data-key` 的按钮并根据 Set 加 `is-hidden`。`bindTipChart` 在图例容器上委托 click，toggle 后重绘。后端与序列计算不动。

**Tech Stack:** vanilla JS、canvas 2D、现有 `tests/test_token_chart.js` 静态源码断言、`node`。

## Global Constraints

- 不改后端、序列计算、缓存或 HTTP 接口
- 不引入 Chart.js / 其它图表 CDN
- 不把可见性写入 localStorage / 设置面板
- 不做 hover 高亮、只留一条、强制至少一条可见
- 模块级 `Set` 默认空（五条全开）；换代币、关 Tip 再开沿用；刷新页面恢复全开
- 不在 `bindTipChart` / `applyTipChartData` / `loadTipTokenChart` 里 `TOKEN_CHART_HIDDEN.clear()`
- 回复与 UI 文案用简体中文
- Windows 上前端断言：`node tests/test_token_chart.js`

## File map

| 文件 | 职责 |
|------|------|
| `web/app.js` | `TOKEN_CHART_HIDDEN`、`toggleTokenChartKey`、绘制跳过、图例按钮、click 委托 |
| `web/styles.css` | 图例按钮与隐藏态（淡化 + 删除线） |
| `tests/test_token_chart.js` | 图例可点、绘制跳过、click 不走榜单刷新 |

---

### Task 1: 隐藏 Set、图例按钮、隐藏样式

**Files:**
- Modify: `web/app.js`（`TOKEN_CHART_LABELS` 之后、`formatChartLegend`）
- Modify: `web/styles.css`（`.row-tip-chart-legend` 之后）
- Test: `tests/test_token_chart.js`

**Interfaces:**
- Consumes: 现有 `TOKEN_CHART_KEYS`、`TOKEN_CHART_COLORS`、`TOKEN_CHART_LABELS`、`fmtKm`、`fmtSignedKm`
- Produces:
  - `TOKEN_CHART_HIDDEN`：`Set<string>`，模块级，默认空
  - `toggleTokenChartKey(key: string) -> boolean`：key 属于 `TOKEN_CHART_KEYS` 时切换并返回 `true`，否则不改 Set 并返回 `false`
  - `formatChartLegend(series) -> string`：五项均为 `<button type="button" class="row-tip-chart-legend-item" data-key="…">`；若 key 在 Set 中再加 `is-hidden`

- [ ] **Step 1: Write the failing test**

在 `tests/test_token_chart.js` 末尾 `console.log("ok");` 之前追加：

```javascript
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node tests/test_token_chart.js`

Expected: FAIL，`TOKEN_CHART_HIDDEN module set`（或同类缺失断言）

- [ ] **Step 3: Write minimal implementation**

在 `web/app.js` 的 `TOKEN_CHART_LABELS` 对象之后插入：

```javascript
const TOKEN_CHART_HIDDEN = new Set();

function toggleTokenChartKey(key) {
  if (!TOKEN_CHART_KEYS.includes(key)) return false;
  if (TOKEN_CHART_HIDDEN.has(key)) TOKEN_CHART_HIDDEN.delete(key);
  else TOKEN_CHART_HIDDEN.add(key);
  return true;
}
```

把 `formatChartLegend` 整段换成：

```javascript
function formatChartLegend(series) {
  const points = Array.isArray(series) ? series : [];
  const last = points.length ? points[points.length - 1] : null;
  return TOKEN_CHART_KEYS.map((key) => {
    const color = TOKEN_CHART_COLORS[key];
    const label = TOKEN_CHART_LABELS[key];
    let val = "—";
    if (last) {
      val = key === "pnl" ? fmtSignedKm(last[key]) : fmtKm(last[key]);
    }
    const hidden = TOKEN_CHART_HIDDEN.has(key) ? " is-hidden" : "";
    return `<button type="button" class="row-tip-chart-legend-item${hidden}" data-key="${key}" style="color:${color}">${label} ${val}</button>`;
  }).join("");
}
```

在 `web/styles.css` 的 `.row-tip-chart-legend` 规则之后、`.row-tip-chart-status` 之前插入：

```css
.row-tip-chart-legend-item {
  appearance: none;
  border: 0;
  background: transparent;
  padding: 0;
  font: inherit;
  color: inherit;
  cursor: pointer;
}

.row-tip-chart-legend-item.is-hidden {
  opacity: 0.4;
  text-decoration: line-through;
}
```

不要在任何加载/刷新函数里 `TOKEN_CHART_HIDDEN.clear()`。

- [ ] **Step 4: Run test to verify it passes**

Run: `node tests/test_token_chart.js`

Expected: PASS，打印 `ok`

- [ ] **Step 5: Commit**

```bash
git add web/app.js web/styles.css tests/test_token_chart.js
git commit -m "Make tip chart legend items togglable buttons."
```

---

### Task 2: 绘制跳过隐藏维度，点击图例切换

**Files:**
- Modify: `web/app.js`（`drawTokenChart` 的 `TOKEN_CHART_KEYS` 循环、`bindTipChart`）
- Test: `tests/test_token_chart.js`

**Interfaces:**
- Consumes: Task 1 的 `TOKEN_CHART_HIDDEN`、`toggleTokenChartKey`、`formatChartLegend`
- Produces:
  - `drawTokenChart(canvas, series)`：`for (const key of TOKEN_CHART_KEYS)` 内首先 `if (TOKEN_CHART_HIDDEN.has(key)) continue;`；坐标轴仍先画；五条都隐藏时只留坐标轴
  - `redrawTipChart(els)`：用 `els.box._series` 调用 `drawTokenChart` + `formatChartLegend`
  - `bindTipChart(row)`：在 `.row-tip-chart-legend` 上委托 click，`closest("[data-key]")` 后 `toggleTokenChartKey` 再 `redrawTipChart(els)`；`stopPropagation`；不调用 `startRefresh` / `setRefreshBusy`

- [ ] **Step 1: Write the failing test**

在 `tests/test_token_chart.js` 末尾 `console.log("ok");` 之前再追加：

```javascript
const drawFn = src.slice(src.indexOf("function drawTokenChart("), src.indexOf("function formatChartLegend("));
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
```

注意：文件里已有一次 `const drawFn = …`。把 Task 1 追加的断言和本段都写在文件后部时，**不要重复声明 `drawFn`**。若 Step 1 执行时 `drawFn` 已在上方定义，本段只追加 `assert(/for \(const key…/` 那条，以及 `redrawTipChart` / `bindFn` 断言。完整后部顺序应为：原有测试 → Task 1 断言 → 本段断言 → `console.log("ok")`。

- [ ] **Step 2: Run test to verify it fails**

Run: `node tests/test_token_chart.js`

Expected: FAIL，`drawTokenChart must skip hidden series`（或 `redrawTipChart missing`）

- [ ] **Step 3: Write minimal implementation**

在 `web/app.js` 的 `drawTokenChart` 里，把：

```javascript
  for (const key of TOKEN_CHART_KEYS) {
    let min = Infinity;
```

改成：

```javascript
  for (const key of TOKEN_CHART_KEYS) {
    if (TOKEN_CHART_HIDDEN.has(key)) continue;
    let min = Infinity;
```

在 `formatChartLegend` 之前插入：

```javascript
function redrawTipChart(els) {
  const series = els?.box?._series || [];
  if (els?.canvas) drawTokenChart(els.canvas, series);
  if (els?.legend) els.legend.innerHTML = formatChartLegend(series);
}
```

把 `bindTipChart` 换成：

```javascript
function bindTipChart(row) {
  const els = tipChartEls(row);
  if (els.canvas) drawTokenChart(els.canvas, []);
  if (els.button) {
    els.button.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      refreshTipTokenChart(row);
    });
  }
  if (els.legend) {
    els.legend.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-key]");
      if (!btn || !els.legend.contains(btn)) return;
      e.preventDefault();
      e.stopPropagation();
      if (!toggleTokenChartKey(btn.getAttribute("data-key"))) return;
      redrawTipChart(els);
    });
  }
  loadTipTokenChart(row);
}
```

`applyTipChartData` 继续调用 `drawTokenChart` / `formatChartLegend` 即可（它们读同一个 Set），不要在刷新路径清空 Set。

- [ ] **Step 4: Run test to verify it passes**

Run: `node tests/test_token_chart.js`

Expected: PASS，打印 `ok`

- [ ] **Step 5: Commit**

```bash
git add web/app.js tests/test_token_chart.js
git commit -m "Skip hidden series when drawing the tip chart."
```
