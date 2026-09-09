# -*- coding: utf-8 -*-
"""Local web app for FOMO Top20 holdings dashboard."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from fomo_auth import auth_status, clear_auth, save_auth, test_auth
from fomo_pipeline import load_cached_result, run_pipeline

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"

app = FastAPI(title="FOMO Desk", version="0.2.0")

_lock = threading.Lock()
_job: dict[str, Any] = {
    "status": "idle",  # idle | running | done | error
    "progress": "",
    "result": None,
    "error": None,
    "mode": None,
}


class AuthPayload(BaseModel):
    accessToken: str = Field(default="", description="Privy Bearer access token")


class RefreshPayload(BaseModel):
    mode: str = Field(default="fast", description="fast | full")


def _set_progress(msg: str) -> None:
    with _lock:
        _job["progress"] = msg


def _run_job(mode: str) -> None:
    try:
        _set_progress(f"开始刷新（{mode}）…")
        result = run_pipeline(progress=_set_progress, mode=mode)
        with _lock:
            _job["status"] = "done"
            _job["result"] = result
            _job["error"] = None
            _job["mode"] = mode
            _job["progress"] = f"完成 · {result.get('tokenCount', 0)} 个代币"
    except Exception as exc:
        with _lock:
            _job["status"] = "error"
            _job["error"] = str(exc)
            _job["progress"] = "失败"


@app.get("/api/health")
def health():
    return {"ok": True, "auth": auth_status()}


@app.get("/api/auth/status")
def api_auth_status():
    return {"ok": True, **auth_status()}


@app.post("/api/auth/token")
def api_auth_save(payload: AuthPayload):
    saved = save_auth(payload.accessToken)
    checked = test_auth()
    return {"ok": True, **saved, "test": checked}


@app.post("/api/auth/clear")
def api_auth_clear():
    clear_auth()
    return {"ok": True, **auth_status()}


@app.get("/api/fomo-top20/cached")
def fomo_cached():
    cached = load_cached_result()
    if not cached:
        return {"ok": False, "rows": [], "columns": [], "message": "暂无缓存，请点击侧边栏刷新"}
    rows = cached.get("rows") or cached.get("tokens") or []
    return {
        "ok": True,
        "updatedAt": cached.get("marketCapUpdatedAt") or cached.get("generatedAt"),
        "traders": cached.get("traders") or [],
        "tokenCount": cached.get("tokenCount") or len(rows),
        "columns": cached.get("columns") or (list(rows[0].keys()) if rows else []),
        "rows": rows,
        "note": cached.get("limitation") or cached.get("note") or "",
        "mode": cached.get("mode") or "fast",
        "source": "cache",
    }


@app.get("/api/fomo-top20/status")
def fomo_status():
    with _lock:
        return {
            "status": _job["status"],
            "progress": _job["progress"],
            "error": _job["error"],
            "hasResult": _job["result"] is not None,
            "mode": _job["mode"],
        }


@app.post("/api/fomo-top20/refresh")
def fomo_refresh(payload: RefreshPayload | None = None):
    mode = (payload.mode if payload else "fast") or "fast"
    mode = "full" if mode == "full" else "fast"
    if mode == "full" and not auth_status().get("configured"):
        raise HTTPException(status_code=400, detail="全量模式需先配置 Privy Access Token")
    with _lock:
        if _job["status"] == "running":
            return {"ok": True, "started": False, "message": "已有任务在运行", "mode": _job.get("mode")}
        _job["status"] = "running"
        _job["progress"] = "排队中…"
        _job["error"] = None
        _job["result"] = None
        _job["mode"] = mode
    threading.Thread(target=_run_job, args=(mode,), daemon=True).start()
    return {"ok": True, "started": True, "mode": mode}


@app.get("/api/fomo-top20/result")
def fomo_result():
    with _lock:
        if _job["status"] == "error":
            raise HTTPException(status_code=500, detail=_job["error"] or "刷新失败")
        if _job["result"] is None:
            cached = load_cached_result()
            if cached:
                rows = cached.get("rows") or cached.get("tokens") or []
                return {
                    "ok": True,
                    "source": "cache",
                    "updatedAt": cached.get("marketCapUpdatedAt") or cached.get("generatedAt"),
                    "traders": cached.get("traders") or [],
                    "tokenCount": cached.get("tokenCount") or len(rows),
                    "columns": cached.get("columns") or (list(rows[0].keys()) if rows else []),
                    "rows": rows,
                    "note": cached.get("note") or cached.get("limitation") or "",
                    "mode": cached.get("mode") or "fast",
                    "stats": cached.get("stats") or {},
                }
            raise HTTPException(status_code=404, detail="尚无结果")
        result = _job["result"]
        return {"ok": True, "source": "live", **result}


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=str(WEB)), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="127.0.0.1", port=8787, reload=False)
