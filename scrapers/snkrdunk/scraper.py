"""スニダン（snkrdunk.com）トレカ価格スクレイパー

/en/v1/search API でトレカ（ポケモンカード・ワンピースカード等）の
シュリンク有商品の最安値を取得する。
JANコードはスニダン側に存在しないため、商品ページの og:title から日本語名を取得し
snkrdunk.json に保存する。フロントエンドで日本語名のカギカッコキーワードでマッチング
して参考価格として表示する。

除外条件:
  商品名に「シュリンクなし」「No shrink」等を含む商品をシュリンク無として除外する。
  isTradingCard=False の非トレカ商品も除外する。
  box_only=True のキーワードは名前に「box」「ボックス」を含まない商品を除外する。

日本語名取得:
  og:title メタタグから取得し「の新品/中古フリマ(通販)｜スニダン」等のサフィックスを除去。
  既存の snkrdunk.json にキャッシュがある場合は再取得しない。
"""

import os
import json
import re
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from scrapers.snkrdunk.config import API_URL, BASE_URL, SEARCH_TARGETS, MIN_PRICE

# シュリンクなし判定キーワード（大文字小文字を無視して照合）
NO_SHRINK_KEYWORDS = [
    "シュリンクなし",
    "シュリンク無し",
    "shrinkなし",
    "no shrink",
    "[no shrink]",
    "【シュリンクなし】",
]

# BOX商品判定キーワード（box_only=True の場合に使用）
BOX_KEYWORDS = ["box", "ボックス"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "application/json",
    "Accept-Language": "ja,en;q=0.9",
    "Referer":         "https://snkrdunk.com/",
}

PER_PAGE        = 50
JA_NAME_WORKERS = 8

_OG_SUFFIX_RE = re.compile(r"\s*の新品.*$|\s*\|.*$")


def _fetch_ja_name(product_id: int, session: requests.Session) -> str | None:
    """商品ページの og:title から日本語名を取得する。"""
    try:
        r = session.get(
            f"{BASE_URL}/apparels/{product_id}",
            headers={**HEADERS, "Accept": "text/html"},
            timeout=15,
        )
        r.raise_for_status()
        # requests は charset 未指定時に ISO-8859-1 を使うため、UTF-8 で明示デコード
        text = r.content.decode("utf-8", errors="replace")
        m = re.search(r'<meta property="og:title" content="([^"]+)"', text)
        if m:
            return _OG_SUFFIX_RE.sub("", m.group(1)).strip()
    except Exception:
        pass
    return None


class SnkrdunkScraper:
    """トレカ シュリンク有商品の参考価格を取得するスクレイパー。"""

    def __init__(self, cache_path: str = "docs/data/snkrdunk.json"):
        self._cache_path = cache_path

    def _load_ja_name_cache(self) -> dict:
        """既存 snkrdunk.json から id→name_ja のキャッシュを読み込む。"""
        if not os.path.exists(self._cache_path):
            return {}
        try:
            with open(self._cache_path, encoding="utf-8") as f:
                data = json.load(f)
            return {item["id"]: item["name_ja"] for item in data.get("items", []) if item.get("name_ja")}
        except Exception:
            return {}

    def _fetch_keyword(self, keyword: str, box_only: bool) -> list:
        """1キーワード分の商品一覧を取得して返す。"""
        results = []
        seen_ids = set()
        page = 1

        while True:
            try:
                resp = requests.get(
                    API_URL,
                    params={"keyword": keyword, "perPage": PER_PAGE, "page": page},
                    headers=HEADERS,
                    timeout=20,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f"[snkrdunk] API 取得失敗 ({keyword} page={page}): {e}", flush=True)
                break

            products = data.get("streetwears", []) + data.get("sneakers", [])
            if not products:
                break

            for p in products:
                name = p.get("name", "")
                name_lower = name.lower()

                if any(kw in name_lower for kw in NO_SHRINK_KEYWORDS):
                    continue
                if not p.get("isTradingCard", False):
                    continue
                if box_only and not any(kw in name_lower for kw in BOX_KEYWORDS):
                    continue

                price = p.get("minPrice")
                if not price or price < MIN_PRICE:
                    continue

                product_id = p.get("id")
                if not product_id or product_id in seen_ids:
                    continue

                seen_ids.add(product_id)
                results.append({
                    "id":      product_id,
                    "name":    name,
                    "name_ja": "",
                    "price":   price,
                    "url":     f"{BASE_URL}/apparels/{product_id}",
                })

            total = (data.get("streetwearCount") or 0) + (data.get("sneakerCount") or 0)
            if page * PER_PAGE >= total or len(products) < PER_PAGE:
                break

            page += 1
            time.sleep(random.uniform(0.8, 1.5))

        return results

    def scrape(self) -> list:
        """SEARCH_TARGETS の全キーワードで商品一覧を取得して返す。"""
        all_results = []
        seen_ids = set()

        for i, target in enumerate(SEARCH_TARGETS):
            keyword  = target["keyword"]
            box_only = target.get("box_only", False)
            # 2件目以降はレートリミット回避のため待機
            if i > 0:
                print(f"[snkrdunk] レートリミット回避のため90秒待機...", flush=True)
                time.sleep(90)
            items = self._fetch_keyword(keyword, box_only)
            # 重複IDを除去（複数キーワードで同一商品が出る場合）
            for item in items:
                if item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    all_results.append(item)
            print(f"[snkrdunk] {keyword}: {len(items)} 件取得", flush=True)

        print(f"[snkrdunk] 合計: {len(all_results)} 件（シュリンク有のみ）", flush=True)

        # 日本語名を取得（キャッシュ済みは再取得しない）
        cache = self._load_ja_name_cache()
        need_fetch = [r for r in all_results if r["id"] not in cache]

        if need_fetch:
            print(f"[snkrdunk] 日本語名を取得中: {len(need_fetch)} 件...", flush=True)
            session = requests.Session()
            session.headers.update({**HEADERS, "Accept": "text/html"})
            lock = threading.Lock()
            fetched = 0

            def fetch_one(item):
                nonlocal fetched
                ja = _fetch_ja_name(item["id"], session)
                with lock:
                    fetched += 1
                    if fetched % 50 == 0:
                        print(f"[snkrdunk] {fetched}/{len(need_fetch)} 件取得済み", flush=True)
                return item["id"], ja

            with ThreadPoolExecutor(max_workers=JA_NAME_WORKERS) as ex:
                futures = {ex.submit(fetch_one, item): item for item in need_fetch}
                for future in as_completed(futures):
                    pid, ja_name = future.result()
                    if ja_name:
                        cache[pid] = ja_name
                    time.sleep(random.uniform(0.1, 0.3))

        for r in all_results:
            r["name_ja"] = cache.get(r["id"], r["name"])

        print(f"[snkrdunk] 取得完了: {len(all_results)} 件", flush=True)
        return all_results
