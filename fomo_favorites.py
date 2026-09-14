# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import threading
from pathlib import Path

from fomo_token_chart import normalize_token_addr

ROOT = Path(__file__).resolve().parent
FAVORITES_PATH = ROOT / "fomo_favorites.json"

_lock = threading.Lock()


def normalize_favorite_addr(addr: str) -> str:
    raw = str(addr or "").strip()
    if not raw:
        raise ValueError("缺少合约地址")
    return normalize_token_addr(raw)


def load_favorites() -> list[str]:
    if not FAVORITES_PATH.exists():
        return []
    try:
        raw = json.loads(FAVORITES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    items = raw.get("addrs") if isinstance(raw, dict) else raw
    out: list[str] = []
    seen: set[str] = set()
    for item in items or []:
        try:
            key = normalize_favorite_addr(item)
        except ValueError:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def save_favorites(addrs: list[str]) -> list[str]:
    FAVORITES_PATH.write_text(
        json.dumps({"addrs": addrs}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return addrs


def toggle_favorite(addr: str) -> tuple[str, bool, list[str]]:
    key = normalize_favorite_addr(addr)
    with _lock:
        addrs = load_favorites()
        if key in addrs:
            addrs = [item for item in addrs if item != key]
            favorited = False
        else:
            addrs = addrs + [key]
            favorited = True
        save_favorites(addrs)
        return key, favorited, addrs
