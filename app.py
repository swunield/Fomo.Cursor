# -*- coding: utf-8 -*-
"""Local web app for FOMO holdings dashboard."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from fomo_auth import auth_status, clear_auth, save_auth, test_auth
from fomo_google_login import login_status, request_cancel, start_google_login
from fomo_oauth import complete_browser_google_oauth, parse_privy_callback, start_browser_google_oauth
from fomo_pipeline import (
    is_cache_fresh,
    load_cached_result,
    load_settings,
    resolve_board,
    run_pipeline,
    save_settings,
)

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"

app = FastAPI(title="FOMO Desk", version="0.3.0")

_lock = threading.Lock()
_job: dict[str, Any] = {
    "status": "idle",  # idle | running | done | error
    "progress": "",
    "result": None,
    "error": None,
    "mode": None,
    "board": "all",
}


class AuthPayload(BaseModel):
    accessToken: str = Field(default="", description="Privy Bearer access token")


class GoogleStartPayload(BaseModel):
    mobile: bool = Field(default=False, description="Phone uses robots.txt OAuth")


class GoogleCompletePayload(BaseModel):
    callback: str = Field(default="", description="fomo.family callback URL or query")


class RefreshPayload(BaseModel):
    mode: str = Field(default="fast", description="fast | full")
    board: str = Field(default="all", description="all | 7d | 24h")
    limit: int | None = Field(default=None, description="override top-N for this run")
    force: bool = Field(default=False, description="ignore 10-minute cache freshness")


class SettingsPayload(BaseModel):
    allLimit: int | None = Field(default=None, description="总榜人数")
    dayLimit: int | None = Field(default=None, description="7日榜人数")
    h24Limit: int | None = Field(default=None, description="24小时榜人数")


def _normalize_board(board: str | None) -> str:
    return resolve_board(board or "all")["boardKey"]


def _set_progress(msg: str) -> None:
    with _lock:
        _job["progress"] = msg


def _run_job(mode: str, board: str, limit: int | None = None) -> None:
    try:
        cfg = resolve_board(board, limit=limit)
        _set_progress(f"开始刷新（{cfg['label']} · {mode}）…")
        result = run_pipeline(
            progress=_set_progress, mode=mode, board=board, limit=cfg["limit"]
        )
        with _lock:
            _job["status"] = "done"
            _job["result"] = result
            _job["error"] = None
            _job["mode"] = mode
            _job["board"] = board
            _job["progress"] = f"完成 · {result.get('tokenCount', 0)} 个代币"
    except Exception as exc:
        with _lock:
            _job["status"] = "error"
            _job["error"] = str(exc)
            _job["progress"] = "失败"


def _payload_from_cached(cached: dict, source: str = "cache") -> dict:
    rows = cached.get("rows") or cached.get("tokens") or []
    return {
        "ok": True,
        "source": source,
        "updatedAt": cached.get("generatedAt") or cached.get("marketCapUpdatedAt"),
        "generatedAt": cached.get("generatedAt") or cached.get("marketCapUpdatedAt"),
        "traders": [],
        "tokenCount": cached.get("tokenCount") or len(rows),
        "columns": cached.get("columns") or (list(rows[0].keys()) if rows else []),
        "rows": rows,
        "note": cached.get("note") or cached.get("limitation") or "",
        "mode": cached.get("mode") or "fast",
        "board": cached.get("board") or "all",
        "boardLabel": cached.get("boardLabel") or "",
        "stats": cached.get("stats") or {},
    }


@app.get("/api/health")
def health():
    return {"ok": True, "auth": auth_status()}


@app.get("/api/auth/status")
def api_auth_status():
    return {"ok": True, **auth_status()}


@app.post("/api/auth/token")
def api_auth_save(payload: AuthPayload):
    raw = payload.accessToken
    if parse_privy_callback(raw).get("authorization_code"):
        try:
            result = complete_browser_google_oauth(raw)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, **result}
    saved = save_auth(raw)
    checked = test_auth()
    return {"ok": True, **saved, "test": checked}


@app.post("/api/auth/clear")
def api_auth_clear():
    clear_auth()
    return {"ok": True, **auth_status()}


@app.post("/api/auth/google/start")
def api_auth_google_start(payload: GoogleStartPayload | None = None):
    mobile = bool(payload.mobile) if payload else False
    try:
        if mobile:
            return start_browser_google_oauth()
        try:
            result = start_google_login()
            return {**result, "mode": "playwright"}
        except Exception as playwright_exc:
            msg = str(playwright_exc)
            if "未找到可用浏览器" in msg or "缺少 playwright" in msg:
                result = start_browser_google_oauth()
                return {**result, "fallback": "browser"}
            raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/auth/google/status")
def api_auth_google_status():
    return login_status()


@app.post("/api/auth/google/cancel")
def api_auth_google_cancel():
    return request_cancel()


@app.post("/api/auth/google/complete")
def api_auth_google_complete(payload: GoogleCompletePayload):
    try:
        return complete_browser_google_oauth(payload.callback)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/settings")
def api_settings_get():
    s = load_settings()
    return {
        "ok": True,
        **s,
        "allLabel": f"总榜前{s['allLimit']}",
        "dayLabel": f"7日榜前{s['dayLimit']}",
        "h24Label": f"24小时榜前{s['h24Limit']}",
    }


@app.post("/api/settings")
def api_settings_save(payload: SettingsPayload):
    s = save_settings(
        all_limit=payload.allLimit,
        day_limit=payload.dayLimit,
        h24_limit=payload.h24Limit,
    )
    return {
        "ok": True,
        **s,
        "allLabel": f"总榜前{s['allLimit']}",
        "dayLabel": f"7日榜前{s['dayLimit']}",
        "h24Label": f"24小时榜前{s['h24Limit']}",
    }


@app.get("/api/fomo-top20/cached")
def fomo_cached(board: str = Query(default="all")):
    board = _normalize_board(board)
    cached = load_cached_result(board=board)
    if not cached:
        return {
            "ok": False,
            "rows": [],
            "columns": [],
            "board": board,
            "message": "暂无缓存，请点击侧边栏刷新",
        }
    return _payload_from_cached(cached)


@app.get("/api/fomo-top20/status")
def fomo_status():
    with _lock:
        return {
            "status": _job["status"],
            "progress": _job["progress"],
            "error": _job["error"],
            "hasResult": _job["result"] is not None,
            "mode": _job["mode"],
            "board": _job.get("board") or "all",
        }


@app.post("/api/fomo-top20/refresh")
def fomo_refresh(payload: RefreshPayload | None = None):
    mode = (payload.mode if payload else "fast") or "fast"
    mode = "full" if mode == "full" else "fast"
    board = _normalize_board(payload.board if payload else "all")
    limit = payload.limit if payload else None
    force = bool(payload.force) if payload else False
    if mode == "full" and not auth_status().get("configured"):
        raise HTTPException(status_code=400, detail="全量模式需先配置 Privy Access Token")
    if not force:
        cached = load_cached_result(board=board)
        if is_cache_fresh(cached):
            body = _payload_from_cached(cached)
            body.update(
                {
                    "ok": True,
                    "started": False,
                    "skipped": True,
                    "reason": "fresh",
                    "board": board,
                }
            )
            return body
    with _lock:
        if _job["status"] == "running":
            return {
                "ok": True,
                "started": False,
                "message": "已有任务在运行",
                "mode": _job.get("mode"),
                "board": _job.get("board"),
            }
        _job["status"] = "running"
        _job["progress"] = "排队中…"
        _job["error"] = None
        _job["result"] = None
        _job["mode"] = mode
        _job["board"] = board
    threading.Thread(target=_run_job, args=(mode, board, limit), daemon=True).start()
    cfg = resolve_board(board, limit=limit)
    return {
        "ok": True,
        "started": True,
        "mode": mode,
        "board": board,
        "limit": cfg["limit"],
        "boardLabel": cfg["label"],
    }


@app.get("/api/fomo-top20/result")
def fomo_result(board: str = Query(default="all")):
    board = _normalize_board(board)
    with _lock:
        if _job["status"] == "error":
            raise HTTPException(status_code=500, detail=_job["error"] or "刷新失败")
        if _job["result"] is None:
            cached = load_cached_result(board=board)
            if cached:
                return _payload_from_cached(cached)
            raise HTTPException(status_code=404, detail="尚无结果")
        result = _job["result"]
        # Prefer live result only when it matches requested board
        if result.get("board") and result.get("board") != board:
            cached = load_cached_result(board=board)
            if cached:
                return _payload_from_cached(cached)
        return {"ok": True, "source": "live", **result}


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=str(WEB)), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8787, reload=False, timeout_keep_alive=75)
