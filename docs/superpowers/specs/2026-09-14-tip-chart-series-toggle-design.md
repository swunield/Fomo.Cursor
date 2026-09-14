# Tips 图表曲线显示/隐藏

日期：2026-09-14

## 目标

持仓轨迹图的五条曲线（市值、人数、数量、持仓市值、盈亏）可通过点击图例单独显示或隐藏，便于看清被叠住的维度。

## 非目标

- 不改后端、序列计算、缓存或 HTTP 接口
- 不引入 Chart.js 等新前端库
- 不把可见性写入 localStorage / 设置面板
- 不做 hover 高亮、只留一条、强制至少一条可见等额外交互

## 交互

图例五项改为可点按钮。点击切换该维度曲线：

- 可见：保持现有配色与最新值
- 隐藏：颜色变淡、文字加删除线，最新值仍显示
- 允许全部关掉，此时只画坐标轴

默认五条全开。

## 状态

模块级 `Set` 记录当前隐藏的 key（`mcap` / `holders` / `amount` / `holdMcap` / `pnl`），默认空。

- 换代币、关 Tip 再开：沿用同一套可见性
- 刷新页面：恢复全开
- 刷新/轮询重绘：沿用当前 Set，图例选中态不丢

## 绘制

`drawTokenChart(canvas, series)` 读取模块级隐藏 Set，循环 `TOKEN_CHART_KEYS` 时跳过其中的 key。每条可见曲线仍按自身 min/max 缩放。

`formatChartLegend` 输出带 `data-key` 的按钮；隐藏项加 CSS class。`bindTipChart` 在图例上委托 click：改 Set 后重绘 canvas 并刷新图例 HTML。

## 测试

在 `tests/test_token_chart.js` 增加静态断言：

- 图例项为可点控件且带 `data-key`
- `drawTokenChart` 会按隐藏集合跳过对应 `strokeStyle` / 折线
- 图例 click 处理存在，且不调用榜单刷新

## 关键文件

| 文件 | 变化 |
|------|------|
| `web/app.js` | 隐藏 Set、绘制跳过、图例按钮与 click |
| `web/styles.css` | 图例按钮、隐藏态（淡化 + 删除线） |
| `tests/test_token_chart.js` | 上述静态断言 |
