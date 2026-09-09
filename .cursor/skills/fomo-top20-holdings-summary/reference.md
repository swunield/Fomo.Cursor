# Fomo总榜前20 — 数据源与字段参考

## 榜单

### 985monitor

- URL: `https://985monitor.xyz/fomo-leaderboards.json`
- 路径: `boards.all`（总榜 All-time）
- 常用字段: `rank`, `handle`, `name`, `pnl`, `followers`, `numTrades`
- `updatedAt` 可能是毫秒时间戳

### peer.family

- 页面展示 Top10/部分榜单，可作交叉核对

## 持仓（spotlight）

### 985monitor profile

- `GET https://985monitor.xyz/api/fomo-watch/profile?handle={handle}`
- 关注 `profitSnapshot` / 开仓列表中的:
  - `tokenAddress`, `symbol`, `network`/`chain`
  - `unrealizedPnlUsd`, `realizedPnlUsd`, `profitUsd`, `profitPercent`
  - `closedAt`（`null` = 未平仓）

### 官方 FOMO API（通常不可用）

- Host 线索: `prod-api.fomo.family`, `app-actions.fomo.family`
- 未授权返回 unauthorized；需要 Privy 会话，不要指望公开拉取完整 `/v2/userTokens`

## 市值

### DexScreener

- `https://api.dexscreener.com/latest/dex/tokens/{addr}`（可逗号批量，建议 ≤30）
- 请求头加 `User-Agent`
- 取 `liquidity.usd` 最高的 pair
- 用 `baseToken.address` 匹配目标合约；**优先 `fdv`（完全稀释市值）**，否则 `marketCap`。FOMO/Meme 语境下的「市值」通常指 FDV（如 BUN 流通市值约 5M、FDV 约 18M）

### GeckoTerminal（ATH 估算）

- 限速约 **30 次/分钟**
- 池子: `/api/v2/networks/{network}/tokens/{address}/pools`
- K 线: `/api/v2/networks/{network}/pools/{pool}/ohlcv/day?aggregate=1&limit=1000`
- network 映射示例: `solana`, `bsc`, `base`, `eth`
- ATH 市值 ≈ `max(high) * (currentMarketCap / currentPrice)`
- 过滤离谱 high（相对中位数或现价的倍数上限，且 ATH 不宜超过当前市值数十倍）

### ATH 缓存

`fomo_mcap_ath_cache.json` 按合约地址记录:

- `athMarketCap`, `athMarketCapTime`
- `lastCurrentMarketCap`, `lastUpdated`

合并逻辑：取「当前市值 / Gecko ATH / 缓存 ATH」中的有效最大值。

## 发射平台推断启发

| 线索 | 平台 |
|------|------|
| 地址后缀 `pump` | pump.fun |
| 地址后缀 `bonk` | LetsBonk |
| chain `robinhood` / Pons | Robinhood Chain / Pons / Pons Launchpad |
| chain `bsc` + pancakeswap | BSC (pancakeswap) |
| chain `base` + uniswap | Base (uniswap) |
| chain `solana` + meteora/raydium/pumpswap | Solana (…) |

## 显示格式解析（回读 CSV 时）

- `12.1M(2.44%)` → 价值部分在 `%` 括号前；解析数值时去掉 `\([^)]*%\)$`
- `K`/`M`/`B` 后缀换算后再比较或重算百分比
