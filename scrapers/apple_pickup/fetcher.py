"""Apple Store 受け取り在庫の取得（1回分）。

check_once() が全地点×型番の在庫を問い合わせ、店舗ごと・型番ごとの状態を返す。
状態は Apple の pickupDisplay と pickupSearchQuote（「受け取れる日 今日」等の文言）から
  today   … 今日受け取れる（文言は「受け取れる日 本日」）
  later   … 明日以降なら受け取れる（「受け取れる日 明日」「受け取れる日 11/2（月）」等）
  none    … 受け取れない（現在ご利用いただけません 等）
の3つに分ける。文言は quote にそのまま残す（判定の見直し用）。
"""

import time

import requests

from scrapers.base import CHROME_HEADERS
from scrapers.apple_pickup.config import (
    ENDPOINT, LOCATIONS, PARTS, PARTS_PER_REQUEST, REQUEST_GAP,
)

_HEADERS = {**CHROME_HEADERS, "Accept": "application/json"}

# これを受けたらブロックとみなし、その回で止める（回避はしない）
BLOCK_STATUSES = {403, 429, 541}


class AppleBlockedError(RuntimeError):
    """Apple がブロック応答（541 等）を返した。"""


def _state(info: dict) -> str:
    """pickupDisplay と文言から today / later / none を決める。"""
    if info.get("pickupDisplay") != "available":
        return "none"
    quote = info.get("pickupSearchQuote") or ""
    # 当日の文言は「受け取れる日 本日」（2026-10-30 実測。「今日」ではない）
    return "today" if ("本日" in quote or "今日" in quote) else "later"


def _chunks(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def check_once(session: requests.Session) -> dict:
    """全店舗の在庫を1回取得する。

    Returns:
        {"stores": {店番号: {"name": 店名, "parts": {型番: {"state": .., "quote": ..}}}},
         "requests": 問い合わせ回数, "bytes": 受信バイト数}
    Raises:
        AppleBlockedError: ブロック応答のとき
        RuntimeError: 応答の形がおかしいとき（店舗が返らない等）
    """
    stores: dict = {}
    n_req = n_bytes = 0
    part_list = list(PARTS)
    first = True
    for location in LOCATIONS:
        for chunk in _chunks(part_list, PARTS_PER_REQUEST):
            if not first:
                time.sleep(REQUEST_GAP)
            first = False
            params = [("pl", "true"), ("location", location)]
            params += [(f"parts.{i}", p) for i, p in enumerate(chunk)]
            resp = session.get(ENDPOINT, params=params, headers=_HEADERS, timeout=30)
            n_req += 1
            n_bytes += len(resp.content)
            if resp.status_code in BLOCK_STATUSES:
                raise AppleBlockedError(f"HTTP {resp.status_code}（location={location}）")
            resp.raise_for_status()
            got = (resp.json().get("body") or {}).get("stores")
            if not got:
                raise RuntimeError(f"店舗が返らない（location={location}）: {resp.text[:200]}")
            for st in got:
                entry = stores.setdefault(st["storeNumber"], {"name": st.get("storeName", ""), "parts": {}})
                for part, info in (st.get("partsAvailability") or {}).items():
                    entry["parts"][part] = {
                        "state": _state(info),
                        "quote": info.get("pickupSearchQuote") or "",
                    }
    return {"stores": stores, "requests": n_req, "bytes": n_bytes}
