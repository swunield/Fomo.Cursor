# -*- coding: utf-8 -*-
"""FOMO authenticated API helpers (Privy Bearer token + optional Cookie)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
AUTH_PATH = ROOT / "fomo_auth.json"
PROD_API = "https://prod-api.fomo.family"
SUPPORTED_CHAINS = "1,56,143,4663,8453,1399811149"
# Cloudflare / FOMO rejects modern curl JA3; chrome110 impersonation works.
CURL_IMPERSONATE = "chrome110"


def load_auth() -> dict:
    if not AUTH_PATH.exists():
        return {}
    try:
        return json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _preview(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 16:
        return "***"
    return f"{token[:8]}…{token[-6:]}"


def parse_auth_blob(raw: str) -> dict:
    """Accept raw token, 'Bearer …', or full 'Copy as cURL' text."""
    text = (raw or "").strip()
    token = ""
    cookie = ""

    # curl -H 'authorization: Bearer xxx' (case-insensitive)
    m = re.search(r"[Aa]uthorization:\s*[Bb]earer\s+([^\s'\"]+)", text)
    if m:
        token = m.group(1).strip()
    if not token:
        m = re.search(r"[Aa]uthorization:\s*([^\s'\"]+)", text)
        if m and not m.group(1).lower().startswith("basic"):
            val = m.group(1).strip()
            token = val[7:].strip() if val.lower().startswith("bearer ") else val

    # curl -b 'a=b; c=d' or -H 'Cookie: ...'
    m = re.search(r"(?:-b|--cookie)\s+'([^']+)'", text)
    if not m:
        m = re.search(r'(?:-b|--cookie)\s+"([^"]+)"', text)
    if m:
        cookie = m.group(1).strip()
    m = re.search(r"Cookie:\s*([^\n\r]+)", text, flags=re.I)
    if m and not cookie:
        cookie = m.group(1).strip().strip("'\"")

    if not token:
        # plain token paste
        line = text.splitlines()[0].strip() if text else ""
        if line.lower().startswith("bearer "):
            token = line[7:].strip()
        elif line.startswith("eyJ"):
            token = line.strip().strip("'\"")

    return {"accessToken": token, "cookie": cookie}


def save_auth(token_or_curl: str, note: str = "") -> dict:
    parsed = parse_auth_blob(token_or_curl)
    token = parsed["accessToken"]
    cookie = parsed["cookie"]
    if not token and not cookie:
        raise ValueError("未解析到 Bearer Token，请粘贴 Token 或完整 Copy as cURL")
    prev = load_auth()
    data = {
        "accessToken": token or prev.get("accessToken") or "",
        "cookie": cookie or prev.get("cookie") or "",
        "note": note
        or "From fomo.family DevTools (Authorization Bearer, optional Cookie)",
    }
    AUTH_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "ok": True,
        "hasToken": bool(data["accessToken"]),
        "hasCookie": bool(data["cookie"]),
        "tokenPreview": _preview(data["accessToken"]),
    }


def clear_auth() -> None:
    if AUTH_PATH.exists():
        AUTH_PATH.unlink()


def get_access_token() -> str | None:
    token = (load_auth().get("accessToken") or "").strip()
    return token or None


def get_cookie() -> str | None:
    cookie = (load_auth().get("cookie") or "").strip()
    return cookie or None


def auth_status() -> dict:
    token = get_access_token()
    cookie = get_cookie()
    return {
        "configured": bool(token or cookie),
        "hasToken": bool(token),
        "hasCookie": bool(cookie),
        "tokenPreview": _preview(token or ""),
        "authPath": str(AUTH_PATH.name),
    }


def fomo_get(path: str, token: str | None = None, timeout: int = 40) -> dict:
    token = token if token is not None else get_access_token()
    cookie = get_cookie()
    if not token and not cookie:
        raise RuntimeError("未配置 FOMO 登录态：请粘贴 Privy Access Token 或 Copy as cURL")
    if not path.startswith("/"):
        path = "/" + path
    url = PROD_API + path
    headers = {
        "accept": "*/*",
        "accept-language": "zh-CN,zh;q=0.9",
        "app-language": "zh",
        "content-type": "application/json",
        "origin": "https://fomo.family",
        "referer": "https://fomo.family/",
        "x-supported-chains": SUPPORTED_CHAINS,
    }
    if token:
        headers["authorization"] = f"Bearer {token}"
    if cookie:
        headers["cookie"] = cookie

    try:
        from curl_cffi import requests as crequests
    except ImportError as exc:
        raise RuntimeError("缺少 curl_cffi，请运行: pip install curl_cffi") from exc

    try:
        resp = crequests.get(
            url,
            headers=headers,
            impersonate=CURL_IMPERSONATE,
            timeout=timeout,
        )
        try:
            body = resp.json()
        except Exception:
            body = {"error": resp.text[:500], "statusCode": resp.status_code}
        if not isinstance(body, dict):
            body = {"responseObject": body, "statusCode": resp.status_code}
        body.setdefault("statusCode", resp.status_code)
        if resp.status_code >= 400 and "error" not in body and "success" not in body:
            body["error"] = body.get("message") or f"HTTP {resp.status_code}"
        return body
    except Exception as exc:
        return {"error": str(exc), "statusCode": 0}


def fetch_user_balances(user_id: str, token: str | None = None) -> list[dict]:
    data = fomo_get(f"/v2/users/{user_id}/balances", token=token)
    status = data.get("statusCode")
    if data.get("error") or status in (401, 403, 430, 431):
        code = status or "?"
        err = data.get("error") or data.get("message") or "unauthorized"
        hint = ""
        if code in (430, 431) or err == "unauthorized":
            hint = (
                " 常见原因：Token 过期，或 TLS 指纹被拦（本项目需 curl_cffi chrome110）。"
                " 请在已登录浏览器中对成功的 prod-api 请求 Copy as cURL，再粘贴到侧边栏。"
            )
        raise RuntimeError(f"balances failed for {user_id}: HTTP {code} {err}.{hint}")

    obj = data.get("responseObject", data)
    if isinstance(obj, dict) and "balances" in obj:
        rows = obj.get("balances") or []
    elif isinstance(obj, list):
        rows = obj
    else:
        rows = data.get("balances") or []
    if not isinstance(rows, list):
        raise RuntimeError(f"unexpected balances shape for {user_id}: {type(obj)}")
    return rows


def parse_balance_item(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    trade = item.get("activeTrade") or {}
    # Only currently open positions
    if trade and trade.get("closedAt") is not None:
        return None

    bal = item.get("balance") or {}
    tfr = item.get("tokenFilterResult") or {}
    token_meta = tfr.get("token") or item.get("token") or {}
    user_token = item.get("userToken") or {}

    addr = (
        bal.get("tokenAddress")
        or token_meta.get("address")
        or user_token.get("tokenAddress")
        or item.get("tokenAddress")
        or ""
    ).strip()
    if not addr:
        return None

    symbol = (
        token_meta.get("symbol")
        or (token_meta.get("info") or {}).get("symbol")
        or tfr.get("symbol")
        or item.get("symbol")
        or ""
    ).strip()
    name = (
        token_meta.get("name")
        or (token_meta.get("info") or {}).get("name")
        or item.get("name")
        or ""
    ).strip()
    network_id = (
        token_meta.get("networkId")
        or user_token.get("networkId")
        or trade.get("networkId")
        or item.get("networkId")
    )

    try:
        price = float(tfr.get("priceUSD") or 0)
    except (TypeError, ValueError):
        price = 0.0

    amount = bal.get("shiftedBalance")
    if amount is None:
        amount = trade.get("humanTokenAmount")
    if amount is None:
        amount = user_token.get("humanAmountRemaining")
    try:
        amount = float(amount or 0)
    except (TypeError, ValueError):
        amount = 0.0

    value = amount * price if price > 0 and amount > 0 else 0.0
    if value <= 0:
        return None

    return {
        "tokenAddress": addr,
        "symbol": symbol,
        "name": name,
        "networkId": network_id,
        "amount": amount,
        "priceUsd": price,
        "value": value,
        "marketCap": float(tfr.get("marketCap") or 0) if tfr.get("marketCap") not in (None, "") else 0,
    }


def balances_to_holdings(rows: list[dict]) -> list[dict]:
    out = []
    for item in rows:
        parsed = parse_balance_item(item)
        if parsed and parsed["value"] > 0:
            out.append(parsed)
    return out


def test_auth(token: str | None = None) -> dict:
    """Probe /config then a public top trader balances endpoint."""
    try:
        data = fomo_get("/config", token=token)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    status = data.get("statusCode")
    if data.get("error") == "unauthorized" or status in (401, 403, 430, 431):
        return {
            "ok": False,
            "error": "unauthorized",
            "statusCode": status,
            "hint": (
                "FOMO 返回 unauthorized。请用浏览器登录后，对状态为 200 的 "
                "prod-api 请求 Copy as cURL 再保存。"
            ),
            "detail": {k: data.get(k) for k in ("error", "message", "statusCode") if k in data},
        }
    if data.get("success") or status in (None, 200) or "responseObject" in data:
        return {"ok": True, "endpoint": "/config", "statusCode": status or 200}
    return {"ok": False, "error": "unexpected", "detail": data}
