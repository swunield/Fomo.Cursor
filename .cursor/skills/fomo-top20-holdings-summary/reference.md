# Fomo总榜前20 — 数据源与字段参考

## 榜单

只使用官方 FOMO API（需 Privy Token）：

- 总榜：`GET https://prod-api.fomo.family/v2/leaderboard`
- 7 日：`GET https://prod-api.fomo.family/v2/leaderboard/7d`
- 24 小时：`GET https://prod-api.fomo.family/v2/leaderboard/24h`

常用字段: `rank`, `userHandle` / `handle`, `displayName`, `id` / `userId`, `totalPnL` / `pnl7d` / `pnl24h`

未授权返回 unauthorized；需要 Privy 会话。TLS 指纹需 `curl_cffi` impersonate，不要用普通 urllib。

## 持仓

`GET https://prod-api.fomo.family/v2/users/{userId}/balances`

关注：

- `shiftedBalance` × `priceUSD` → 持仓市值
- `activeTrade.closedAt`（非空则已平仓，跳过）
- `tokenFilterResult`：市值、成交量、24h 涨跌、创建时间

## 市值

登录拉取 balances 时写入 `fomo_token_meta_cache.json`。日常展示优先读该缓存。

`fomo_mcap_ath_cache.json` 按合约地址记录:

- `athMarketCap`, `athMarketCapTime`
- `lastCurrentMarketCap`, `lastUpdated`

合并逻辑：取「当前市值 / 缓存 ATH」中的有效最大值。

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
