"""買取商店（kaitorishouten-co.jp）スクレイパー（bg-worker 版・JSON API 方式）

経緯:
  2026-09-04 にサイトが React SPA（Vite ビルド）へ全面刷新され、旧構成が依存していた
  AJAX エンドポイント（/products/list_keitai_new 等）・カテゴリ HTML（/products/2/list_category）・
  sitemap の /category/{n}/ が全て消えた（どの URL も SPA の index.html を返す）。
  旧スクレイパーは例外を出さずに「0件」を返し続け、run_kaitorishouten.py の 0件ガードで
  前回データを保持したまま 13 日間更新が止まっていた。

現行の取得方法（API 優先）:
  フロント（/assets/real-*.js）が使う公開 JSON API をそのまま叩く。認証・Cookie 不要。
    GET /api/v1/products?per_page=100&perPage=100&page=N
      {"items":[...], "page":N, "per_page":100, "total":7710}
  1ページ 100 件固定・約 0.4 秒応答。全 78 ページを逐次取得しても 1〜2 分で終わるため、
  旧構成の fast/full（部分取得＋前回値合成）の区別は不要になった。scrape(mode) の引数は
  互換のため残しているが、どちらでも全件スナップショットを返す。

item の主なフィールド:
  id            … 商品 ID（/products/detail/{id}）
  name          … 商品名（色は「黒/銀/青/紫」のような1文字表記）
  jan           … JAN（無い商品が約 5% ある → スキップ）
  category      … "スマホ" / "家電" / "おもちゃ" / "お酒" / None
  price_undecided … 価格未定（prices が空）→ スキップ
  price_new     … {"amount": 新品の基準価格, ...} または None
  prices[]      … [{"label": "新品" | "新品 未開封" | "新品 ※来店 +5000円" | "中古" | ..., "amount": int}, ...]

採用価格（旧 HTML 版の div.item-price.plain-price ＝ 新品の基準価格に合わせる）:
  1. price_new.amount があればそれ
  2. 無ければ label が「新品」ちょうどの amount
  3. それも無ければ label が「新品」で始まり「+」「-」の増減表記を含まない amount の最大
  4. 中古のみの商品（約 3%）は採用しない（本サイトは未開封品の比較が目的）
"""

import random
import re
import time

from scrapers.base import BaseScraper, CHROME_HEADERS
from scrapers.common import extract_jan, merge_into_results
from scrapers.kaitorishouten.config import (
    SITE_ID, SITE_NAME, BASE_URL, API_PRODUCTS_URL, API_PER_PAGE, PRODUCT_URL,
    PAGE_DELAY_MIN, PAGE_DELAY_MAX, MAX_PAGES,
)

# API 呼び出し時のヘッダー。ブラウザの fetch と同じ見え方にする（Referer は一覧ページ）
_API_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Referer": BASE_URL + "/products/list",
    "X-Requested-With": "XMLHttpRequest",
}

# 「新品 ※来店 +5000円」「新品 傷有 -4000円」のような増減付きラベルを除外する
_ADJUSTED_LABEL_RE = re.compile(r"[+＋\-−－]\s*[\d,]+\s*円")


def _pick_new_price(item: dict) -> int | None:
    """item から新品の基準価格を選ぶ（モジュール docstring の採用順）。"""
    price_new = item.get("price_new") or {}
    amount = price_new.get("amount")
    if isinstance(amount, (int, float)) and amount > 0:
        return int(amount)

    prices = item.get("prices") or []
    for p in prices:
        if p.get("label") == "新品" and (p.get("amount") or 0) > 0:
            return int(p["amount"])

    candidates = [
        int(p["amount"])
        for p in prices
        if str(p.get("label", "")).startswith("新品")
        and not _ADJUSTED_LABEL_RE.search(str(p.get("label", "")))
        and (p.get("amount") or 0) > 0
    ]
    return max(candidates) if candidates else None


class KaitorishoutenScraper(BaseScraper):
    site_id   = SITE_ID
    site_name = SITE_NAME

    def _sleep(self):
        """ページ間のランダムウェイト（固定間隔パターンを避ける）。"""
        time.sleep(random.uniform(PAGE_DELAY_MIN, PAGE_DELAY_MAX))

    def _fetch_page(self, page: int) -> dict:
        """API の 1 ページを取得して JSON を返す。失敗時は最大 3 回リトライ。"""
        params = {"per_page": API_PER_PAGE, "perPage": API_PER_PAGE, "page": page}
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                resp = self.session.get(
                    API_PRODUCTS_URL, params=params,
                    headers={**CHROME_HEADERS, **_API_HEADERS}, timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, dict) or "items" not in data:
                    raise ValueError(f"想定外のレスポンス形式: {str(data)[:120]}")
                return data
            except Exception as exc:  # 接続エラー・5xx・JSON 不正
                last_error = exc
                wait = 10 * (attempt + 1)
                print(f"  [kaitorishouten] page={page} 失敗({attempt + 1}/3): {exc} → {wait}秒待機", flush=True)
                time.sleep(wait)
        raise RuntimeError(f"page={page} リトライ上限到達: {last_error}")

    def _parse_items(self, items: list[dict], results: dict) -> tuple[int, int, int]:
        """API の items を results にマージし (採用, JAN なし, 新品価格なし) の件数を返す。"""
        taken = no_jan = no_price = 0
        for item in items:
            jan = extract_jan(str(item.get("jan") or ""))
            if not jan:
                no_jan += 1
                continue
            price = _pick_new_price(item)
            if not price:
                no_price += 1
                continue
            name = re.sub(r"\s+", " ", str(item.get("name") or "")).strip()
            if not name:
                continue
            url = PRODUCT_URL.format(item.get("id")) if item.get("id") else BASE_URL + "/products/list"
            merge_into_results(results, jan, name, price, url)
            taken += 1
        return taken, no_jan, no_price

    def scrape(self, mode: str = "full") -> dict:
        """全商品を API から取得して JAN → 価格情報の辞書を返す。

        mode は旧 fast/full 互換のために受け取るだけで、どちらも全件スナップショット。
        途中のページで例外が出た場合はそのまま上げ、呼び出し側（run_kaitorishouten.py）が
        部分データで上書きしないようにする。
        """
        results: dict = {}
        totals = {"taken": 0, "no_jan": 0, "no_price": 0}

        first = self._fetch_page(1)
        total = int(first.get("total") or 0)
        per_page = int(first.get("per_page") or API_PER_PAGE) or API_PER_PAGE
        max_page = max(1, -(-total // per_page))  # 切り上げ
        if max_page > MAX_PAGES:
            raise RuntimeError(f"ページ数が上限を超過: {max_page} > {MAX_PAGES}（total={total}）")
        print(f"[kaitorishouten] API: total={total} per_page={per_page} pages={max_page} (mode={mode})", flush=True)

        for page in range(1, max_page + 1):
            data = first if page == 1 else self._fetch_page(page)
            items = data.get("items") or []
            if not items:
                # total より早く尽きた＝取得中に商品が減った。以降は無いので打ち切る
                print(f"  [kaitorishouten] page={page} が空のため打ち切り", flush=True)
                break
            taken, no_jan, no_price = self._parse_items(items, results)
            totals["taken"] += taken
            totals["no_jan"] += no_jan
            totals["no_price"] += no_price
            if page % 10 == 0 or page == max_page:
                print(f"  [kaitorishouten] page={page}/{max_page} 累計 {len(results)} JANs", flush=True)
            if page < max_page:
                self._sleep()

        print(
            f"[kaitorishouten] 完了: {len(results)} JANs"
            f"（採用 {totals['taken']} / JANなし {totals['no_jan']} / 新品価格なし {totals['no_price']}）",
            flush=True,
        )
        return results
