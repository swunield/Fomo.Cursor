# 代币持仓人交易轨迹图 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在代币 Tip 底部（布局 B）画出该币追踪交易员的 5 条持仓轨迹；默认读服务端缓存，只有点图表「刷新」才拉 `/trades/{id}`。

**Architecture:** 纯函数在 `fomo_token_chart.py` 里把 swap/transfer 滚成时间序列并按合约地址落盘。`app.py` 用独立于榜单 `_job` 的 per-addr 后台任务提供 GET/POST。前端 canvas 自绘，不引用 Chart.js。

**Tech Stack:** Python 3.11、unittest、FastAPI TestClient、vanilla JS、canvas 2D、既有 `fomo_get`/`curl_cffi`。

## Global Constraints

- 不改 CSV 列顺序：`名称,市值,成交量,天数,24h涨跌,持仓人数,持仓市值,持仓盈亏,人均持仓市值,创建时间,最高持仓人,最高持仓市值,最低持仓人,最低持仓市值,所有持仓人,发射平台,合约地址`
- 榜单/汇总刷新路径不得请求 `/trades/`
- 不引入 Chart.js / 其它图表 CDN
- 当时市值 = 成交价 × **当前**流通量（`marketCap / priceUsd`）
- 缓存目录 `fomo_token_trades/` 不进 git、不随 `deploy/push.py` 上传
- 图表刷新不得调用 `setRefreshBusy` / `startRefresh` / `startRefreshSummary`
- 回复与 UI 文案用简体中文
- Windows 上测试命令用 `python -m unittest …` 与 `node tests/….js`

## File map

| 文件 | 职责 |
|------|------|
| `fomo_token_chart.py` | 事件、序列、缓存、增量计划、refresh 编排 |
| `tests/test_token_chart.py` | 上述纯函数与 FastAPI GET/POST |
| `fomo_auth.py` | `fetch_trade`；`parse_balance_item` 增加 `tradeId` |
| `fomo_pipeline.py` | 持仓行写入 `holders`（含 uid/tradeId/amount） |
| `app.py` | `GET/POST /api/fomo-top20/token-chart` |
| `web/app.js` / `web/styles.css` / `web/index.html` | Tip 布局 B、canvas、只读缓存/点刷新 |
| `tests/test_token_chart.js` | Tip DOM 与「刷新不走榜单」静态断言 |
| `deploy/push.py` | `SKIP_DIRS` 增加 `fomo_token_trades`、`.superpowers` |
| `.gitignore` | 已含 `fomo_token_trades/`；若缺失则补上 |

---

### Task 1: 交易事件与滚动序列

**Files:**
- Create: `fomo_token_chart.py`
- Test: `tests/test_token_chart.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `normalize_token_addr(addr: str) -> str`
  - `circulating_supply(market_cap: float, price_usd: float) -> float`
  - `iter_trade_events(token_address: str, user_id: str, user_address: str, trade_obj: dict) -> list[dict]`
    - 每项：`{"t": str, "userId": str, "qty": float, "usd": float, "price": float}`；`qty` 买入/转入为正、卖出/转出为负
  - `build_series(token_address: str, circulating_supply: float, traders: dict) -> list[dict]`
    - 点：`{"t", "mcap", "holders", "amount", "holdMcap", "pnl"}`
  - 常量 `DUST_AMOUNT = 1e-9`

- [ ] **Step 1: Write the failing test**

在 `tests/test_token_chart.py` 写入：

```python
# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest

from fomo_token_chart import build_series, circulating_supply, iter_trade_events


TOKEN = "So1AAA"
USER = "u1"
WALLET = "Wallet1"


def _traders(swaps=None, transfers=None, user_address=WALLET):
    return {
        USER: {
            "userId": USER,
            "handle": "alice",
            "displayName": "Alice",
            "trades": {
                "t1": {
                    "id": "t1",
                    "updatedAt": "2026-09-13T00:00:00Z",
                    "closedAt": None,
                    "userAddress": user_address,
                    "swaps": swaps or [],
                    "transfers": transfers or [],
                }
            },
        }
    }


class CirculatingSupplyTests(unittest.TestCase):
    def test_divides_mcap_by_price(self):
        self.assertEqual(circulating_supply(1000.0, 0.5), 2000.0)

    def test_zero_price_is_zero(self):
        self.assertEqual(circulating_supply(1000.0, 0.0), 0.0)


class IterTradeEventsTests(unittest.TestCase):
    def test_buy_swap_positive_qty(self):
        events = iter_trade_events(
            TOKEN,
            USER,
            WALLET,
            {
                "swaps": [
                    {
                        "id": "s1",
                        "createdAt": "2026-09-11T11:00:00Z",
                        "outTokenAddress": TOKEN,
                        "outHumanAmount": 100,
                        "inTokenAddress": "USDC",
                        "inHumanAmount": 50,
                        "humanUsdAmountIn": 50,
                        "humanUsdAmountOut": 50,
                    }
                ],
                "transfers": [],
            },
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["qty"], 100)
        self.assertEqual(events[0]["usd"], 50)
        self.assertEqual(events[0]["price"], 0.5)

    def test_sell_swap_negative_qty(self):
        events = iter_trade_events(
            TOKEN,
            USER,
            WALLET,
            {
                "swaps": [
                    {
                        "id": "s2",
                        "createdAt": "2026-09-11T12:00:00Z",
                        "inTokenAddress": TOKEN,
                        "inHumanAmount": 40,
                        "outTokenAddress": "USDC",
                        "outHumanAmount": 30,
                        "humanUsdAmountIn": 30,
                        "humanUsdAmountOut": 30,
                    }
                ],
                "transfers": [],
            },
        )
        self.assertEqual(events[0]["qty"], -40)
        self.assertEqual(events[0]["usd"], 30)

    def test_transfer_direction_by_address(self):
        events = iter_trade_events(
            TOKEN,
            USER,
            WALLET,
            {
                "swaps": [],
                "transfers": [
                    {
                        "id": "tr1",
                        "createdAt": "2026-09-11T13:00:00Z",
                        "tokenAddress": TOKEN,
                        "toAddress": WALLET,
                        "fromAddress": "Other",
                        "humanAmount": 10,
                        "usdAmount": 4,
                    }
                ],
            },
        )
        self.assertEqual(events[0]["qty"], 10)
        self.assertEqual(events[0]["usd"], 4)


class BuildSeriesTests(unittest.TestCase):
    def test_buy_then_sell_updates_holders_amount_pnl(self):
        traders = _traders(
            swaps=[
                {
                    "id": "s1",
                    "createdAt": "2026-09-11T11:00:00Z",
                    "outTokenAddress": TOKEN,
                    "outHumanAmount": 100,
                    "inTokenAddress": "USDC",
                    "humanUsdAmountIn": 50,
                    "humanUsdAmountOut": 50,
                },
                {
                    "id": "s2",
                    "createdAt": "2026-09-11T12:00:00Z",
                    "inTokenAddress": TOKEN,
                    "inHumanAmount": 100,
                    "outTokenAddress": "USDC",
                    "humanUsdAmountIn": 80,
                    "humanUsdAmountOut": 80,
                },
            ]
        )
        series = build_series(TOKEN, circulating_supply=1000.0, traders=traders)
        self.assertEqual(len(series), 2)
        first, last = series[0], series[1]
        self.assertEqual(first["holders"], 1)
        self.assertEqual(first["amount"], 100)
        self.assertEqual(first["holdMcap"], 50)  # 100 * 0.5
        self.assertEqual(first["mcap"], 500)  # 0.5 * 1000
        self.assertEqual(last["holders"], 0)
        self.assertEqual(last["amount"], 0)
        self.assertEqual(last["pnl"], 30)  # sold 80 vs cost 50

    def test_same_timestamp_keeps_last_snapshot(self):
        traders = _traders(
            swaps=[
                {
                    "id": "s1",
                    "createdAt": "2026-09-11T11:00:00.000Z",
                    "outTokenAddress": TOKEN,
                    "outHumanAmount": 10,
                    "humanUsdAmountIn": 10,
                    "humanUsdAmountOut": 10,
                },
                {
                    "id": "s2",
                    "createdAt": "2026-09-11T11:00:00.000Z",
                    "outTokenAddress": TOKEN,
                    "outHumanAmount": 5,
                    "humanUsdAmountIn": 5,
                    "humanUsdAmountOut": 5,
                },
            ]
        )
        series = build_series(TOKEN, 100.0, traders)
        self.assertEqual(len(series), 1)
        self.assertEqual(series[0]["amount"], 15)

    def test_emptied_trader_still_affects_history(self):
        traders = _traders(
            swaps=[
                {
                    "id": "s1",
                    "createdAt": "2026-09-11T11:00:00Z",
                    "outTokenAddress": TOKEN,
                    "outHumanAmount": 10,
                    "humanUsdAmountIn": 10,
                    "humanUsdAmountOut": 10,
                },
                {
                    "id": "s2",
                    "createdAt": "2026-09-11T12:00:00Z",
                    "inTokenAddress": TOKEN,
                    "inHumanAmount": 10,
                    "humanUsdAmountIn": 10,
                    "humanUsdAmountOut": 10,
                },
            ]
        )
        series = build_series(TOKEN, 100.0, traders)
        self.assertEqual(series[0]["holders"], 1)
        self.assertEqual(series[1]["holders"], 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_token_chart -v`

Expected: FAIL，`ModuleNotFoundError: fomo_token_chart`

- [ ] **Step 3: Write minimal implementation**

创建 `fomo_token_chart.py`，实现：

- `normalize_token_addr`：`strip` + `lower`
- `circulating_supply`：`price_usd > 0` 时 `market_cap / price_usd` 否则 `0.0`
- `iter_trade_events`：
  - 比较地址时用 `normalize_token_addr`
  - swap：`outTokenAddress == token` → `qty = +outHumanAmount`，`usd = humanUsdAmountIn or humanUsdAmountOut`；`inTokenAddress == token` → `qty = -inHumanAmount`，`usd = humanUsdAmountOut or humanUsdAmountIn`
  - transfer：仅当 `tokenAddress` 匹配；`toAddress == user_address` → 正；`fromAddress == user_address` → 负；`usd = usdAmount`；数量 `humanAmount`
  - `price = usd / abs(qty)`，qty 或 usd 无效则 `price = 0`
- `build_series`：
  - 从每个 `trades[*]` 取 `userAddress`（缺省用 trader 上的 `userAddress`）调用 `iter_trade_events`
  - 按 `t` 升序；每人 `amount/cost/realized = 0`
  - 正 qty：`amount += qty`，`cost += usd`
  - 负 qty：`sold = min(amount, -qty)`；若 `amount > 0` 则 `cost_cut = cost * (sold / amount)`，`realized += usd * (sold / -qty if -qty else 1) - cost_cut`（卖出数量等于 `-qty` 且不超过持仓时：`realized += usd - cost_cut`）；`cost -= cost_cut`；`amount -= sold`
  - 有效 `price > 0` 更新 `last_price`，否则沿用
  - 每人 `amount > DUST_AMOUNT` 计入 holders
  - `pnl = Σ(pos.amount * last_price - pos.cost + pos.realized)`
  - 同一 `t` 只保留该秒处理完后的最后快照

卖出实现用这套，保证「买 100@0.5 卖 100@0.8 → pnl 30」：

```python
sold = min(pos["amount"], -qty)
frac = sold / pos["amount"] if pos["amount"] else 0.0
proceeds = usd * (sold / (-qty)) if qty < 0 and -qty else usd
cost_cut = pos["cost"] * frac
pos["realized"] += proceeds - cost_cut
pos["cost"] -= cost_cut
pos["amount"] -= sold
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_token_chart -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add fomo_token_chart.py tests/test_token_chart.py
git commit -m "$(cat <<'EOF'
Add token trade event series reconstruction.

EOF
)"
```

若用户未要求提交则跳过 commit，继续下一任务。

---

### Task 2: 缓存合并与增量跳过

**Files:**
- Modify: `fomo_token_chart.py`
- Test: `tests/test_token_chart.py`

**Interfaces:**
- Consumes: Task 1 的 `build_series`、`normalize_token_addr`
- Produces:
  - `TRADES_DIR` = 仓库根目录 / `fomo_token_trades`
  - `empty_cache(addr: str) -> dict`（`traders: {}`, `series: []`, `lastFetchedAt: None`, `circulatingSupply: 0`）
  - `load_token_trades(addr: str, *, root: Path | None = None) -> dict`
  - `save_token_trades(addr: str, data: dict, *, root: Path | None = None) -> None`
  - `should_skip_trade(cached_trade: dict | None, incoming_updated_at: str | None) -> bool`
  - `plan_trade_fetches(cache: dict, holders: list[dict]) -> list[dict]`
    - 返回待拉项 `{"userId","handle","displayName","tradeId"}`
  - `merge_fetched_trade(cache: dict, holder: dict, payload: dict) -> None`（按 swap/transfer `id` 合并，保留已清仓 trader）
  - `apply_series(cache: dict, token_address: str, circulating_supply: float) -> dict`（写 `series` 后返回 cache）

- [ ] **Step 1: Write the failing test**

追加到 `tests/test_token_chart.py`：

```python
from pathlib import Path
from tempfile import TemporaryDirectory

from fomo_token_chart import (
    empty_cache,
    load_token_trades,
    merge_fetched_trade,
    plan_trade_fetches,
    save_token_trades,
    should_skip_trade,
)


class SkipTradeTests(unittest.TestCase):
    def test_skip_when_closed(self):
        self.assertTrue(
            should_skip_trade({"closedAt": "2026-09-01T00:00:00Z", "updatedAt": "a"}, "b")
        )

    def test_skip_when_updated_at_matches(self):
        ts = "2026-09-13T00:00:00Z"
        self.assertTrue(should_skip_trade({"closedAt": None, "updatedAt": ts}, ts))

    def test_fetch_when_updated_at_changes(self):
        self.assertFalse(
            should_skip_trade(
                {"closedAt": None, "updatedAt": "2026-09-13T00:00:00Z"},
                "2026-09-13T01:00:00Z",
            )
        )

    def test_fetch_when_missing_cache(self):
        self.assertFalse(should_skip_trade(None, "2026-09-13T00:00:00Z"))


class PlanFetchesTests(unittest.TestCase):
    def test_unions_current_holders_and_cached_closed_trades(self):
        cache = empty_cache(TOKEN)
        cache["traders"][USER] = {
            "userId": USER,
            "handle": "alice",
            "displayName": "Alice",
            "trades": {
                "old": {
                    "id": "old",
                    "updatedAt": "2026-09-01T00:00:00Z",
                    "closedAt": "2026-09-02T00:00:00Z",
                    "swaps": [],
                    "transfers": [],
                }
            },
        }
        holders = [
            {
                "uid": "u2",
                "handle": "bob",
                "name": "Bob",
                "tradeId": "new",
                "tradeUpdatedAt": "2026-09-13T00:00:00Z",
            }
        ]
        planned = plan_trade_fetches(cache, holders)
        ids = {p["tradeId"] for p in planned}
        self.assertIn("new", ids)
        self.assertNotIn("old", ids)  # closedAt 已有则跳过

    def test_skips_holder_without_trade_id(self):
        cache = empty_cache(TOKEN)
        planned = plan_trade_fetches(
            cache, [{"uid": "u9", "handle": "x", "name": "X", "tradeId": ""}]
        )
        self.assertEqual(planned, [])


class MergeAndDiskTests(unittest.TestCase):
    def test_keeps_emptied_trader_and_merges_swaps_by_id(self):
        cache = empty_cache(TOKEN)
        holder = {"uid": USER, "handle": "alice", "name": "Alice", "tradeId": "t1"}
        merge_fetched_trade(
            cache,
            holder,
            {
                "userId": USER,
                "userHandle": "alice",
                "displayName": "Alice",
                "trade": {
                    "id": "t1",
                    "updatedAt": "2026-09-13T01:00:00Z",
                    "closedAt": "2026-09-13T02:00:00Z",
                    "userAddress": WALLET,
                },
                "swaps": [{"id": "s1", "createdAt": "2026-09-11T11:00:00Z"}],
                "transfers": [],
            },
        )
        merge_fetched_trade(
            cache,
            holder,
            {
                "userId": USER,
                "trade": {
                    "id": "t1",
                    "updatedAt": "2026-09-13T03:00:00Z",
                    "closedAt": "2026-09-13T02:00:00Z",
                    "userAddress": WALLET,
                },
                "swaps": [
                    {"id": "s1", "createdAt": "2026-09-11T11:00:00Z"},
                    {"id": "s2", "createdAt": "2026-09-11T12:00:00Z"},
                ],
                "transfers": [],
            },
        )
        swaps = cache["traders"][USER]["trades"]["t1"]["swaps"]
        self.assertEqual({s["id"] for s in swaps}, {"s1", "s2"})
        self.assertIsNotNone(cache["traders"][USER]["trades"]["t1"]["closedAt"])

    def test_roundtrip_missing_file_is_empty_series(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            loaded = load_token_trades(TOKEN, root=root)
            self.assertEqual(loaded["series"], [])
            self.assertIsNone(loaded["lastFetchedAt"])
            loaded["series"] = [{"t": "x", "mcap": 1, "holders": 1, "amount": 1, "holdMcap": 1, "pnl": 0}]
            save_token_trades(TOKEN, loaded, root=root)
            again = load_token_trades(TOKEN, root=root)
            self.assertEqual(len(again["series"]), 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_token_chart.SkipTradeTests tests.test_token_chart.PlanFetchesTests tests.test_token_chart.MergeAndDiskTests -v`

Expected: FAIL，函数未定义

- [ ] **Step 3: Write minimal implementation**

在 `fomo_token_chart.py` 实现上述函数：

- 磁盘路径：`(root or 仓库根) / "fomo_token_trades" / f"{normalize_token_addr(addr)}.json"`
- `should_skip_trade`：`cached_trade` 有非空 `closedAt` → True；双方 `updatedAt` 非空且字符串相等 → True；否则 False
- `plan_trade_fetches`：
  - 建 `seen` 集合
  - 遍历 `holders`：无 `tradeId` 则计入 `cache.setdefault("_missingTradeIds", 0)` 但不加入 planned（函数也可把 missing 计数放返回值外的 cache 字段；测试只断言 planned 为空）
  - 对每个有 `tradeId` 的 holder 与 cache 里每个 trade：调用 `should_skip_trade(cached, holder.get("tradeUpdatedAt"))`；cache 里没有对应 holder 的 `tradeUpdatedAt` 时，仅 `closedAt` 可跳过，否则加入 planned
  - 清仓缓存项：`closedAt` 已有则不拉
- `merge_fetched_trade`：按 `userId`（payload.userId 或 holder.uid）写入 `traders`；`swaps`/`transfers` 用 id 字典合并；写入 `userAddress` 从 `payload["trade"]["userAddress"]`
- `load_token_trades`：文件不存在返回 `empty_cache`；坏 JSON 同样返回 empty
- 确认 `.gitignore` 含 `fomo_token_trades/`

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_token_chart -v`

Expected: PASS（含 Task 1）

- [ ] **Step 5: Commit**

```bash
git add fomo_token_chart.py tests/test_token_chart.py .gitignore
git commit -m "$(cat <<'EOF'
Cache token trades per contract and skip unchanged ids.

EOF
)"
```

---

### Task 3: `fetch_trade` 与持仓 `tradeId`

**Files:**
- Modify: `fomo_auth.py`（`fomo_get` 附近、`parse_balance_item` 返回值）
- Modify: `fomo_pipeline.py`（`token_map` append 与 `rows` 构造）
- Test: `tests/test_token_chart.py`（parse_balance_item）；可补 `tests/test_holding_pnl.py` 若 CSV 列测试被 holders 字段干扰——`DictWriter extrasaction=ignore` 已忽略多余列，CSV 测试不应失败

**Interfaces:**
- Consumes: `fomo_get`
- Produces:
  - `fetch_trade(trade_id: str, token: str | None = None) -> dict` → FOMO `responseObject`（含 `trade/swaps/transfers`）；失败 raise `RuntimeError`
  - `parse_balance_item` 增加 `"tradeId": str`（`activeTrade.id`，无则 `""`）
  - 每个 `token_map` holder 增加 `tradeId`、`amount`、`uid`
  - 每个汇总 `row["holders"]`：`[{rank,name,handle,uid,tradeId,amount,value,pnlUsd}]`，排序与持仓明细相同（按 value 降序）

- [ ] **Step 1: Write the failing test**

```python
from fomo_auth import parse_balance_item


class ParseBalanceTradeIdTests(unittest.TestCase):
    def test_open_position_keeps_trade_id(self):
        item = {
            "balance": {"tokenAddress": "So1AAA", "shiftedBalance": 10},
            "tokenFilterResult": {"priceUSD": "2", "marketCap": "100", "token": {"symbol": "AAA", "address": "So1AAA"}},
            "userToken": {"averageEntryPriceUsd": 1, "currentCostBasisUsd": 10},
            "activeTrade": {"id": "trade-1", "closedAt": None},
        }
        parsed = parse_balance_item(item)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["tradeId"], "trade-1")

    def test_closed_position_still_none(self):
        item = {
            "balance": {"tokenAddress": "So1AAA", "shiftedBalance": 10},
            "tokenFilterResult": {"priceUSD": "2", "marketCap": "100", "token": {"symbol": "AAA"}},
            "activeTrade": {"id": "trade-1", "closedAt": "2026-09-01T00:00:00Z"},
        }
        self.assertIsNone(parse_balance_item(item))
```

再加一个针对 `token_map_to_rows` 的测试：构造单 holder（含 tradeId/uid/amount/value），断言 `rows[0]["holders"][0]["tradeId"] == "trade-1"` 且 `"合约地址"` 仍在、`CSV_COLUMNS` 未新增列。

若 `token_map_to_rows` 名字不是这个，用 `fomo_pipeline.py` 里实际把 `token_map` 变成 `rows` 的函数（当前为该文件中构造 `row = {` 的那段，函数名以源码为准，计划实现时打开 `fomo_pipeline.py` 搜 `持仓明细`）。

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_token_chart.ParseBalanceTradeIdTests -v`

Expected: FAIL，`tradeId` KeyError 或不等

- [ ] **Step 3: Write minimal implementation**

`parse_balance_item` 返回值增加：

```python
"tradeId": str(trade.get("id") or "").strip(),
```

`fomo_auth.py`：

```python
def fetch_trade(trade_id: str, token: str | None = None) -> dict:
    trade_id = (trade_id or "").strip()
    if not trade_id:
        raise RuntimeError("empty trade id")
    data = fomo_get(f"/trades/{trade_id}", token=token)
    status = data.get("statusCode")
    if data.get("error") or status in (401, 403, 430, 431) or not data.get("success", True):
        raise RuntimeError(data.get("error") or data.get("message") or f"trade {trade_id} failed")
    obj = data.get("responseObject")
    if not isinstance(obj, dict):
        raise RuntimeError(f"unexpected trade shape for {trade_id}")
    return obj
```

`fomo_pipeline.py` 的 `token_map[...].append({...})` 增加 `tradeId`、`amount`（`h["amount"]`）。

构造 `row` 时：

```python
"holders": [
    {
        "rank": h["rank"],
        "name": h["name"],
        "handle": h.get("handle") or "",
        "uid": h.get("uid") or "",
        "tradeId": h.get("tradeId") or "",
        "amount": float(h.get("amount") or 0),
        "value": float(h.get("value") or 0),
        "pnlUsd": h.get("pnlUsd"),
    }
    for h in sorted(holders, key=lambda x: float(x.get("value") or 0), reverse=True)
],
```

不要把 `holders` 写入 `CSV_COLUMNS`。`persist_outputs` 已 `extrasaction="ignore"`。

- [ ] **Step 4: Run tests**

Run: `python -m unittest tests.test_token_chart tests.test_holding_pnl tests.test_age_days -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add fomo_auth.py fomo_pipeline.py tests/test_token_chart.py
git commit -m "$(cat <<'EOF'
Persist holder tradeId on board rows for chart refresh.

EOF
)"
```

---

### Task 4: HTTP GET/POST 与后台刷新

**Files:**
- Modify: `fomo_token_chart.py`（`refresh_token_chart`）
- Modify: `app.py`
- Modify: `deploy/push.py`（`SKIP_DIRS` 加 `fomo_token_trades`、`.superpowers`）
- Test: `tests/test_token_chart.py`

**Interfaces:**
- Consumes: `plan_trade_fetches`、`merge_fetched_trade`、`apply_series`/`build_series`、`load_token_trades`、`save_token_trades`、`fetch_trade`、`circulating_supply`；token meta 用 `fomo_auth.load_token_meta_cache`（若函数名不同，用现有读 `fomo_token_meta_cache.json` 的函数）
- Produces:
  - `refresh_token_chart(addr, holders, *, fetch_fn, root=None, circulating=None, progress_fn=None) -> dict`
    - 返回 cache 字典，含 `series`、`lastFetchedAt`、`stats: {fetched, skipped, failed, missingTradeIds}`
  - `GET /api/fomo-top20/token-chart?addr=`
    - `{ ok: true, addr, lastFetchedAt, series, running, progress: {fetched, total}, warning? }`
    - 无文件：`series: []`, `lastFetchedAt: null`, `running: false`, HTTP 200
  - `POST /api/fomo-top20/token-chart/refresh` body `TokenChartRefreshPayload`
    - `{ addr: str, holders: list[{uid, handle, name, tradeId, tradeUpdatedAt?}] }`
    - 未登录：401
    - 该 addr 已 running：`{ ok: false, running: true }` HTTP 200
    - 否则启动后台线程，立即 `{ ok: true, started: true, running: true }`
  - 后台线程**不得**改榜单 `_job`

- [ ] **Step 1: Write the failing tests**

```python
from unittest.mock import patch
from fastapi.testclient import TestClient


class RefreshOrchestrationTests(unittest.TestCase):
    def test_fetch_fn_called_only_for_open_changed_trades(self):
        from fomo_token_chart import empty_cache, merge_fetched_trade, refresh_token_chart

        addr = TOKEN
        cache = empty_cache(addr)
        merge_fetched_trade(
            cache,
            {"uid": USER, "handle": "alice", "name": "Alice", "tradeId": "old"},
            {
                "userId": USER,
                "trade": {
                    "id": "old",
                    "updatedAt": "2026-09-01T00:00:00Z",
                    "closedAt": "2026-09-02T00:00:00Z",
                    "userAddress": WALLET,
                },
                "swaps": [],
                "transfers": [],
            },
        )
        calls = []

        def fetch_fn(trade_id):
            calls.append(trade_id)
            return {
                "userId": "u2",
                "userHandle": "bob",
                "displayName": "Bob",
                "trade": {
                    "id": trade_id,
                    "updatedAt": "2026-09-13T00:00:00Z",
                    "closedAt": None,
                    "userAddress": "Wallet2",
                },
                "swaps": [
                    {
                        "id": "s1",
                        "createdAt": "2026-09-11T11:00:00Z",
                        "outTokenAddress": addr,
                        "outHumanAmount": 10,
                        "humanUsdAmountIn": 10,
                        "humanUsdAmountOut": 10,
                    }
                ],
                "transfers": [],
            }

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_token_trades(addr, cache, root=root)
            out = refresh_token_chart(
                addr,
                [
                    {
                        "uid": "u2",
                        "handle": "bob",
                        "name": "Bob",
                        "tradeId": "new",
                        "tradeUpdatedAt": "2026-09-13T00:00:00Z",
                    }
                ],
                fetch_fn=fetch_fn,
                root=root,
                circulating=100.0,
            )
        self.assertEqual(calls, ["new"])
        self.assertTrue(out["traders"][USER]["trades"]["old"]["closedAt"])
        self.assertIn("new", out["traders"]["u2"]["trades"])
        self.assertGreaterEqual(len(out["series"]), 1)
        self.assertEqual(out["stats"]["fetched"], 1)


class TokenChartApiTests(unittest.TestCase):
    def test_get_missing_returns_empty_series(self):
        from fastapi.testclient import TestClient
        import app as appmod

        with TemporaryDirectory() as tmp:
            with patch("fomo_token_chart.TRADES_DIR", Path(tmp) / "fomo_token_trades"):
                client = TestClient(appmod.app)
                res = client.get("/api/fomo-top20/token-chart", params={"addr": "SoNoSuch"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["series"], [])
        self.assertIsNone(body["lastFetchedAt"])
        self.assertFalse(body["running"])

    def test_second_post_while_running_returns_running(self):
        import app as appmod
        from fastapi.testclient import TestClient

        client = TestClient(appmod.app)
        started = []

        def fake_refresh(*args, **kwargs):
            import time
            started.append(1)
            time.sleep(0.3)
            return empty_cache("x")

        with patch("app.get_access_token", return_value="tok"), patch(
            "app.refresh_token_chart", side_effect=fake_refresh
        ):
            r1 = client.post(
                "/api/fomo-top20/token-chart/refresh",
                json={"addr": "SoLock", "holders": [{"uid": "u", "tradeId": "t"}]},
            )
            r2 = client.post(
                "/api/fomo-top20/token-chart/refresh",
                json={"addr": "SoLock", "holders": [{"uid": "u", "tradeId": "t"}]},
            )
        self.assertTrue(r1.json().get("started") or r1.json().get("running"))
        self.assertTrue(r2.json().get("running"))
        self.assertFalse(r2.json().get("ok", True) and r2.json().get("started"))
```

`get_access_token` 的 patch 目标以 `app.py` 实际 import 为准：若 POST 里 `from fomo_auth import get_access_token`，patch `fomo_auth.get_access_token`。

实现时让 `refresh_token_chart` 可测：先 `load`，`planned = plan_trade_fetches`，对 planned 调 `fetch_fn`，失败计入 `stats.failed` 并保留旧 trade，成功 `merge_fetched_trade`，最后 `build_series` + `save`。

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_token_chart.RefreshOrchestrationTests tests.test_token_chart.TokenChartApiTests -v`

Expected: FAIL

- [ ] **Step 3: Write minimal implementation**

`refresh_token_chart`：

```python
def refresh_token_chart(addr, holders, *, fetch_fn, root=None, circulating=None, progress_fn=None):
    cache = load_token_trades(addr, root=root)
    planned = plan_trade_fetches(cache, holders)
    stats = {"fetched": 0, "skipped": 0, "failed": 0, "missingTradeIds": 0}
    stats["missingTradeIds"] = sum(1 for h in holders or [] if not str(h.get("tradeId") or "").strip())
    stats["skipped"] = (
        sum(len(t.get("trades") or {}) for t in (cache.get("traders") or {}).values())
        + len(holders or [])
        - stats["missingTradeIds"]
        - len(planned)
    )
    total = len(planned)
    for i, item in enumerate(planned, start=1):
        if progress_fn:
            progress_fn(i - 1, total)
        try:
            payload = fetch_fn(item["tradeId"])
            merge_fetched_trade(cache, item, payload)
            stats["fetched"] += 1
        except Exception:
            stats["failed"] += 1
        if progress_fn:
            progress_fn(i, total)
    supply = float(circulating or cache.get("circulatingSupply") or 0)
    cache["circulatingSupply"] = supply
    cache["series"] = build_series(addr, supply, cache.get("traders") or {})
    cache["lastFetchedAt"] = datetime.now(timezone.utc).isoformat()
    cache["stats"] = stats
    save_token_trades(addr, cache, root=root)
    return cache
```

`app.py`：

- 模块级 `_chart_lock = threading.Lock()`，`_chart_jobs: dict[str, dict]` 键为 `normalize_token_addr(addr)`，值 `{status, fetched, total, error}`
- GET：读 `_chart_jobs` + `load_token_trades`；`warning` 在 `stats.missingTradeIds > 0` 时为 `"请先刷新榜单"`
- POST：无 token → 401；addr 空 → 400；若 job status==running → `{ok:False, running:True}`；否则设 running 并 `threading.Thread(target=..., daemon=True)` 调 `refresh_token_chart(..., fetch_fn=fetch_trade, circulating=从 token meta 算, progress_fn=写 _chart_jobs)`
- 流通量：`load_token_meta_cache()` 里该 addr 的 `marketCap/priceUsd`，没有则 0
- Pydantic：

```python
class TokenChartHolder(BaseModel):
    uid: str = ""
    handle: str = ""
    name: str = ""
    tradeId: str = ""
    tradeUpdatedAt: str | None = None

class TokenChartRefreshPayload(BaseModel):
    addr: str
    holders: list[TokenChartHolder] = []
```

`deploy/push.py` 的 `SKIP_DIRS` 增加 `"fomo_token_trades"`、`".superpowers"`。

- [ ] **Step 4: Run tests**

Run: `python -m unittest tests.test_token_chart tests.test_board_refresh -v`

Expected: PASS。`test_second_post_while_running` 若线程太快，拉长 `sleep` 或用 `threading.Event` 在 fake_refresh 里 wait。

- [ ] **Step 5: Commit**

```bash
git add app.py fomo_token_chart.py tests/test_token_chart.py deploy/push.py
git commit -m "$(cat <<'EOF'
Add token-chart cache API with per-address refresh lock.

EOF
)"
```

---

### Task 5: Tip 布局 B 与 canvas 曲线

**Files:**
- Modify: `web/app.js`（`cloneTokenRow`、`mergeSummaryPayloads`、`showRowTip`、新绘图函数）
- Modify: `web/styles.css`
- Modify: `web/index.html`（`app.js?v=` / `styles.css?v=` 从当前值 bump 一位，例如 `20260913m` → `20260913n`）
- Test: `tests/test_token_chart.js`

**Interfaces:**
- Consumes: GET/POST `/api/fomo-top20/token-chart`
- Produces:
  - `TOKEN_CHART_COLORS = { mcap:"#c8f542", holders:"#6ec8ff", amount:"#ffb347", holdMcap:"#d48cff", pnl:"#ff6b6b" }`
  - `drawTokenChart(canvas, series)` — `series` 空则只画坐标轴
  - `formatChartLegend(series)` — 用最新点 + `fmtKm`/`fmtSignedKm`
  - `showRowTip` 在持仓人列表**之后**插入图表区块
  - `loadTipTokenChart(row)` 打开 Tip 时 GET，不 POST
  - `refreshTipTokenChart(row)` 仅由图表按钮触发；POST 后轮询 GET 直到 `running===false`；进度文案 `已拉 n/m`
  - `cloneTokenRow` 深拷贝 `holders`
  - `mergeSummaryPayloads` 按 `uid` 或 `handle` 合并 `holders`，较新 payload 覆盖 `tradeId`

- [ ] **Step 1: Write the failing test**

创建 `tests/test_token_chart.js`：

```javascript
const fs = require("fs");
const path = require("path");
const src = fs.readFileSync(path.join(__dirname, "..", "web", "app.js"), "utf8");

function assert(cond, label) {
  if (!cond) throw new Error(label);
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

const cloneFn = src.slice(src.indexOf("function cloneTokenRow("), src.indexOf("function finalizeMergedRow("));
assert(cloneFn.includes("holders"), "cloneTokenRow must copy holders");

console.log("ok");
```

若 `refreshTipTokenChart` 在 `loadTipTokenChart` 之前，按实际切片；断言核心是 refresh 函数体不含 `startRefresh` / `setRefreshBusy`。

- [ ] **Step 2: Run test to verify it fails**

Run: `node tests/test_token_chart.js`

Expected: FAIL，`drawTokenChart missing`

- [ ] **Step 3: Write minimal implementation**

`showRowTip` 在 holders 的 `</div>` 之后、关闭按钮之前插入：

```html
<div class="row-tip-chart" data-addr="${escapeHtml(addr)}">
  <div class="row-tip-chart-head">
    <span>持仓轨迹</span>
    <button type="button" class="row-tip-chart-refresh" data-addr="${escapeHtml(addr)}">刷新</button>
  </div>
  <canvas class="row-tip-chart-canvas" width="640" height="160"></canvas>
  <div class="row-tip-chart-legend"></div>
  <div class="row-tip-chart-status">无缓存</div>
</div>
```

`addr = row["合约地址"]`。`showRowTip` 末尾 `bindTipChart(row)`：给刷新按钮 `click`（`preventDefault/stopPropagation`）→ `refreshTipTokenChart(row)`；然后 `loadTipTokenChart(row)`。

`drawTokenChart(canvas, series)`：

- 清空；画底/轴
- `keys = ["mcap","holders","amount","holdMcap","pnl"]`
- 每个 key 计算 min/max，映射到 padding 后的高度；x 按 index 均分（若要用时间，用 `Date.parse(p.t)` 的 min/max）
- 点少于 2：只画轴
- `lineTo` 各色

`loadTipTokenChart`：`GET /api/fomo-top20/token-chart?addr=`，画 `series`，无点则 status「无缓存」，有 `lastFetchedAt` 则写时间；`running` 则进入轮询。

`refreshTipTokenChart`：禁用该按钮，`POST` body `{ addr, holders: row.holders || [] }`；`started/running` 后每 900ms GET 直到 `!running`；status 用 `已拉 ${fetched}/${total}`；失败写 `err` 短句并仍 `drawTokenChart` 旧 series；结束启用按钮。`missingTradeIds` 时附加「请先刷新榜单」。

`cloneTokenRow`：

```javascript
out.holders = Array.isArray(row.holders) ? row.holders.map((h) => ({ ...h })) : [];
```

`mergeSummaryPayloads`：在 token 行合并时同时按 holder id（`uid` 小写或 `handle` 小写）合并 `holders`，`t` 更新的 payload 覆盖 `tradeId`/`amount`/`value`。

CSS（沿用 Tip 深色）：

```css
.row-tip-chart { margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--line); }
.row-tip-chart-head { display: flex; justify-content: space-between; align-items: center; color: var(--muted); margin-bottom: 6px; }
.row-tip-chart-refresh { ...与 .refresh-btn 相近的小按钮 }
.row-tip-chart-canvas { width: 100%; height: 140px; display: block; background: #0d120f; border-radius: 8px; }
.row-tip-chart-legend { display: flex; flex-wrap: wrap; gap: 6px 10px; margin-top: 6px; font-size: 10px; }
.row-tip-chart-status { color: var(--muted); font-size: 11px; margin-top: 4px; }
```

bump `web/index.html` 的 `?v=`。

- [ ] **Step 4: Run tests**

Run: `node tests/test_token_chart.js`  
Run: `node tests/test_summary_board.js`

Expected: 都 `ok`

浏览器：打开 `http://127.0.0.1:8787/`，点一行打开 Tip，确认图表在持仓人下方、默认空轴、点图表刷新时顶部榜单刷新按钮状态不变。本机 `app.py` 若 `reload=False`，改后端后需重启。

- [ ] **Step 5: Commit**

```bash
git add web/app.js web/styles.css web/index.html tests/test_token_chart.js
git commit -m "$(cat <<'EOF'
Draw holder trade path chart under token tips.

EOF
)"
```

---

## Spec coverage

| 规格条目 | 任务 |
|----------|------|
| 布局 B、空轴、图上刷新、五色图例 | Task 5 |
| 市值估算、swap/transfer 方向、滚动持仓、同毫秒合并 | Task 1 |
| 本地 JSON 缓存、清仓保留、增量 skip | Task 2 |
| tradeId 来自 activeTrade、CSV 不变 | Task 3 |
| GET 空 series、POST 独立 job、running 互斥、missing tradeId 提示 | Task 4 |
| 榜单刷新不拉 /trades | Task 3–5（测试与代码路径均不调用） |
| 不引入 Chart.js | Task 5 |
| gitignore / 不部署缓存 | Task 2、Task 4 |

## 执行注意

改 `app.py` 后必须重启 `python app.py`。前端只 bump `?v=`。不要把 `fomo_token_trades/` 提交或 `push.py` 上传。
