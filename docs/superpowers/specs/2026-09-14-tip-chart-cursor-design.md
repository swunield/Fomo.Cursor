# Tips 图表时间轴虚线

日期：2026-09-14

## 目标

在持仓轨迹图（canvas）上点选或长按，钉一根从 X 轴垂直向上的虚线；图例显示该时间点的市值 / 人数 / 数量 / 持仓市值 / 盈亏。再点一次取消，回到最新一点。

## 非目标

- 不改后端、序列计算、缓存或 HTTP
- 不引入 Chart.js 等新库
- 不做插值（不对两点之间估算数值）
- 不把选中点写入 localStorage / 设置
- 不改图例曲线显隐

## 交互

只响应 `.row-tip-chart-canvas`（不含图例、刷新、关闭）。

| 手势 | 无虚线 | 已有虚线 |
|------|--------|----------|
| 单击（按下后移动 &lt; 8px，且未满 400ms） | 钉在最近数据点 | 取消，图例回到最新 |
| 长按约 400ms，或按下后滑动 ≥ 8px | 画出虚线并跟随指针 | 虚线移到指针下并跟随 |
| 松手 | 停在最后位置 | 停在最后位置 |

数值对齐最近序列点（与绘制用的 `xAt` / 时间轴同一套 x 映射）。选中时图例旁显示该点时间（`MM-DD HH:mm`）。换代币或关掉 Tip 后状态丢弃。后台刷新曲线时把下标夹紧到新序列范围内，尽量保住选中。

## 绘制

`drawTokenChart(canvas, series, cursorIndex)`：曲线画完后，若 `cursorIndex` 有效，从绘图区底边（X 轴）画到顶边，浅色虚线 `setLineDash([4, 3])`。

`formatChartLegend(series, cursorIndex)`：`cursorIndex == null` 用最后一点且不显示时间；否则用该下标的值并加时间。

## 测试

`tests/test_token_chart.js`：

- `nearestChartIndex` 选最近 x
- 图例按 cursor 取值
- `drawTokenChart` 含虚线
- canvas 绑定 pointerdown / 长按或滑动进入跟随；单击切换；不触发榜单刷新
