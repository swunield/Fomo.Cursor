# 代币持仓人交易轨迹图

日期：2026-09-13

## 目标

在代币 Tip 中展示该币**追踪交易员**的持仓轨迹图。数据来自 `GET /trades/{activeTrade.id}`（swap + transfer）。默认只读本地缓存；无缓存画空坐标轴。只有点击图表上的「刷新」才拉交易。清仓过的人仍留在该币档案里，用于完整轨迹。

## 非目标

- 榜单/汇总刷新时不拉交易
- 不改 CSV 列顺序与展示格式
- 不引入 Chart.js 等新前端库
- 不使用历史流通量时间序列（当时市值用成交价 × **当前**流通量估算）
- 第一次图表刷新之前已经清仓、且从未出现在持仓缓存里的人，无法补全

## 布局

布局 **B**：Tip 现有信息与持仓人列表不变，图表放在持仓人下方。

- 图表标题右侧有「刷新」按钮
- 无缓存：空坐标轴 + 「无缓存」提示
- 刷新中：按钮禁用，图表区显示进度（已拉 n/m 人），Tip 不关闭
- 失败：保留上次曲线（若有），图表区显示错误短句
- 五条曲线各自按自身最小/最大值缩放；图例用原单位显示最新点
- 配色：市值 `#c8f542`，人数 `#6ec8ff`，持仓总数 `#ffb347`，持仓总市值 `#d48cff`，持仓总盈亏 `#ff6b6b`
- 图表刷新不占用榜单「刷新」按钮的 busy 状态

## 数据来源

- 交易：`GET https://prod-api.fomo.family/trades/{tradeId}`，`tradeId` 来自 balances 的 `activeTrade.id`
- 请求头与现有 `fomo_get` 相同（Bearer + `curl_cffi` impersonate）
- 接口一次返回该笔交易全部 `swaps`、`transfers`，没有 `since` 参数。增量策略见下节
- 流通量：`token_meta.marketCap / token_meta.priceUsd`（当前值）
- 事件价格：swap 为 USD÷代币数量；transfer 为 `usdAmount / humanAmount`；价格无效则沿用上一有效价

## 持仓 JSON 增补

榜单刷新时，在每个代币行增加结构化持仓人（CSV 仍只用原列）：

```json
"holders": [
  {
    "rank": 1,
    "name": "Unipcs",
    "handle": "unipcs",
    "uid": "…",
    "tradeId": "61ec7995-…",
    "amount": 28024128.2,
    "value": 1234567.8,
    "pnlUsd": 773645.47
  }
]
```

`parse_balance_item` 增加 `tradeId`（`activeTrade.id`）。`closedAt` 非空的持仓仍不进入榜单行，但图表缓存一旦见过该 `tradeId` 就永久保留。

## 服务端缓存

路径：`fomo_token_trades/<合约地址小写>.json`（gitignore，不部署覆盖）。

```json
{
  "tokenAddress": "…",
  "circulatingSupply": 1.0,
  "lastFetchedAt": "ISO-8601",
  "traders": {
    "<userId>": {
      "userId": "…",
      "handle": "unipcs",
      "displayName": "Unipcs",
      "trades": {
        "<tradeId>": {
          "id": "…",
          "updatedAt": "ISO-8601",
          "closedAt": null,
          "swaps": [],
          "transfers": []
        }
      }
    }
  },
  "series": [
    {
      "t": "ISO-8601",
      "mcap": 0,
      "holders": 0,
      "amount": 0,
      "holdMcap": 0,
      "pnl": 0
    }
  ]
}
```

合并规则：当前行 `holders` ∪ 缓存 `traders`。同一 `userId` 可有多个 `tradeId`（平仓后再开新仓）。swap/transfer 按 `id` 去重合并。

## 增量拉取

刷新某币时，待拉集合 = 当前持仓人的 `tradeId` ∪ 缓存中该币全部 `tradeId`。

对每个 `tradeId`：

1. 缓存已有 `closedAt` → 跳过
2. 当前持仓带来的 `activeTrade.updatedAt` 与缓存 `updatedAt` 相同 → 跳过
3. 否则 `GET /trades/{id}`，用新 `updatedAt`/`closedAt` 覆盖，swap/transfer 按 id 并入

无法跳过时必须拉全量交易对象（API 限制）。

当前行缺少 `tradeId`（旧缓存）：该持仓人本轮跳过，图表区提示「请先刷新榜单」；不因此中止已有 `tradeId` 的拉取。

## 序列计算

1. 将所有追踪交易员的 swap、transfer 合成事件，按 `createdAt` 升序
2. 判断该币增减：swap 若 `outTokenAddress` 为该币则买入，`inTokenAddress` 为该币则卖出；transfer 若 `toAddress` 为该用户则增加数量，`fromAddress` 为该用户则减少数量（与 `type` 文案无关，只看地址方向）
3. 每人维护 `amount`、`cost`、`realizedPnl`
   - 买入/转入：`amount += qty`，`cost += usd`
   - 卖出/转出：按比例减少 `cost`，差额计入 `realizedPnl`，`amount -= qty`（不低于 0）
4. 每个事件之后记一个点：
   - `mcap` = 当时价格 × 流通量
   - `holders` = `amount > 1e-9` 的人数
   - `amount` = 所有人代币数量之和
   - `holdMcap` = `amount * price`
   - `pnl` = Σ(`amount * price - cost + realizedPnl`)
5. 同一毫秒多笔事件合并为最后一个快照

## HTTP 接口

- `GET /api/fomo-top20/token-chart?addr=`
  - 有缓存：`{ ok, addr, lastFetchedAt, series }`
  - 无缓存：`{ ok, addr, lastFetchedAt: null, series: [] }`（HTTP 200）
- `POST /api/fomo-top20/token-chart/refresh`
  - body：`{ addr, holders: [{ uid, handle, name, tradeId, tradeUpdatedAt? }] }`
  - 需已登录；按上节增量拉交易、写盘、返回与 GET 相同形状 + `stats`（fetched/skipped/failed）
  - 与榜单 job 分开；同一 `addr` 已在刷新时，后到的 POST 立即返回 `{ ok: false, running: true }`，不打断榜单刷新

前端：打开 Tip 时 GET 画图；点图表刷新才 POST。刷新 busy 仅作用于该 Tip 内按钮。

## 测试

- 事件排序与滚动持仓：买入/卖出/转入后的人数、数量、市值、盈亏
- 增量跳过：`closedAt` 已有、`updatedAt` 未变不请求
- 清仓用户仍留在 `traders` 并进入后续序列
- GET 无文件返回空 `series`
- Tip 含图表容器且默认在持仓人下方；刷新按钮不调用榜单 `startRefresh`

## 关键文件

| 文件 | 变化 |
|------|------|
| `fomo_auth.py` | `fetch_trade(trade_id)` |
| `fomo_token_chart.py` | 缓存、增量、序列（新建） |
| `fomo_pipeline.py` / `parse_balance_item` | 写出 `tradeId`、`amount`、`holders` |
| `app.py` | GET/POST |
| `web/app.js` / `web/styles.css` | Tip 布局 B、canvas 曲线 |
| `tests/test_token_chart.py`、`tests/test_token_chart.js` | 上述用例 |
| `.gitignore` | `fomo_token_trades/` |
