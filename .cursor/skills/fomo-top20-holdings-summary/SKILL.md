---
name: fomo-top20-holdings-summary
description: >-
  汇总 FOMO 总榜（All-time PnL）前20交易员持仓，按代币聚合导出 CSV/JSON/Markdown，
  并更新代币当前/最高市值。在用户提到 FOMO 总榜前20、持仓汇总、fomo.family、
  985monitor、update_token_marketcap，或说「Fomo总榜前20数据汇总」时使用。
---

# Fomo总榜前20数据汇总

## 目标

把 FOMO **总收益榜前 20** 的持仓按**代币**聚合，导出并维护：

- `fomo_top20_holdings_by_token.csv`
- `fomo_top20_holdings_by_token.json`
- `fomo_top20_holdings_by_token.md`

市值刷新：`update_token_marketcap.py` / `update_token_marketcap.bat`

## 工作流

### 1. 拉取总榜前 20

优先公开源（官方 `prod-api.fomo.family` 需 Privy 登录，通常不可用）：

- `https://985monitor.xyz/fomo-leaderboards.json` → `boards.all[:20]`
- 备选：`peer.family` 榜单页

记录：`rank`、`handle`、`name`、`pnl`

### 2. 拉取各账户持仓代理数据

FOMO 完整持仓接口需登录。用 985monitor 画像 spotlight：

- `https://985monitor.xyz/api/fomo-watch/profile?handle={handle}`
- 取 `profitSnapshot` 中**未平仓**仓位（`closedAt is null`）

估算持仓市值（约等于成本 + 未实现盈亏）：

```
若 profitPercent > 0 且 unrealizedPnlUsd != 0:
  value = unrealized / (pct/100) + unrealized
否则用 profitUsd / (pct/100) + profitUsd；再不行则用未实现盈亏兜底
```

每人通常只有头部盈利仓，**不是完整持仓**。导出时在 JSON `limitation` 中说明。

### 3. 按代币聚合

每个代币一行，字段含义：

| 列 | 计算 |
|----|------|
| 持仓市值 | 各持仓人估算市值之和 |
| 持仓人数 | 持有该代币的 Top20 人数 |
| 人均持仓市值 | 持仓市值 / 人数 |
| 所有持仓人 | 按榜单排名排序的 `排名.昵称` |
| 最高/最低持仓人+价值 | 该代币持仓人中市值最大/最小者 |

发射平台：按链 / 合约后缀（如 `pump`→pump.fun、`bonk`→LetsBonk）/ DexScreener `dexId`+`chainId` 推断。

### 4. 补市值

- **持仓来源**：登录态一律用 FOMO `balances` 实时开仓；未登录才用 985monitor spotlight（可能把已平仓仍标为 open）
- **当前市值 / 成交量 / 24h涨跌 / 创建时间**：登录时来自 FOMO `balances.tokenFilterResult`，写入 `fomo_token_meta_cache.json`；未登录只读缓存。**不再请求 DexScreener/Gecko**

日常只刷新市值时运行：

```bash
python update_token_marketcap.py
# 或双击 update_token_marketcap.bat
```

### 5. 写出文件

必须遵守下方**列顺序与显示格式**（与 `.cursor/rules/fomo-holdings-csv.mdc`、脚本 `CSV_COLUMNS` 一致）。写完同步 CSV、JSON、MD。

## 固定列顺序

```
名称,市值,成交量,24h涨跌,持仓市值,持仓人数,人均持仓市值,创建时间,最高持仓人,最高持仓市值,最低持仓人,最低持仓市值,所有持仓人,发射平台,合约地址
```

## 显示格式

- **市值列**（持仓市值、人均持仓市值、市值、成交量）：`≥1M` → 一位小数 `M`；`≥1K` → 整数 `K`；更小用整数（例：`37.6M`、`887K`）
- **24h涨跌**：`+12.34%` / `-5.67%`
- **最高/最低持仓市值**：`{市值}({占市值%})`，例：`12.1M(2.44%)`
- **持仓人列**：一律 `排名.昵称`，例：`9.ogle`；所有持仓人空格分隔：`1.Unipcs 6.Vee 7.AJC`

Windows 输出设 `PYTHONIOENCODING=utf-8`。

## 关键文件

| 文件 | 用途 |
|------|------|
| `update_token_marketcap.py` | 刷新市值/ATH，规范化显示，写 CSV/JSON/MD |
| `update_token_marketcap.bat` | Windows 一键运行 |
| `fomo_mcap_ath_cache.json` | ATH 本地缓存（勿当脏文件删掉后不重建） |
| `fomo_token_meta_cache.json` | FOMO balances 行情缓存（市值/成交量/24h涨跌） |
| `fomo_mcap_live_cache.json` | （旧）DexScreener 市值缓存，可忽略 |
| `tmp_profiles.json` / `tmp_dex_meta.json` | 调试缓存，可删 |

## 全量持仓（方案 A：Privy Token）

个人主页持仓来自官方：

`GET https://prod-api.fomo.family/v2/users/userHandle/{handle}` → 用户资料（`id`=UUID）  
`GET https://prod-api.fomo.family/v2/users/{userId}/balances` → 持仓 + `tokenFilterResult` 行情

请求头需：

```
Authorization: Bearer <Privy accessToken>
x-supported-chains: 1,56,143,4663,8453,1399811149
app-language: zh
```

**重要：** FOMO/Cloudflare 会按 TLS 指纹拦普通 `urllib`/`curl`（常返回 HTTP 430）。本项目用 `curl_cffi` + `impersonate=chrome110` 请求。

本项目：

1. 网页侧边栏粘贴 Token 或整段 Copy as cURL → 保存到本地 `fomo_auth.json`（勿提交）
2. 点「全量持仓」走 `mode=full`
3. 用 985monitor 的 `userId` + 你的 Token 拉每人 balances（`shiftedBalance * priceUSD`；跳过 `activeTrade.closedAt` 非空）

Token 获取：登录 [fomo.family](https://fomo.family/) → F12 Network → 任意 `prod-api.fomo.family` 请求 → Copy as cURL（推荐）或复制 `Authorization: Bearer …`

Token 会过期，失效后重新粘贴。依赖：`pip install -r requirements.txt`（含 `curl_cffi`）。

## 详细参考

数据源与字段说明见 [reference.md](reference.md)。
