"""森森買取（morimori-kaitori.jp）スクレイパー

GitHub Actions 上で実行（VPS IP ブロックを回避するため）。

サイト構造:
  - カテゴリ一覧: /sitemap.xml から /category/{cat_id}/product/{id} パターンを抽出
  - 商品一覧:    /category/{cat_id}?page=N
  - 1ページの件数が PAGE_SIZE 未満なら最終ページ

カテゴリ取得:
  sitemap.xml から /category/{cat_id}/product/{id} パターンを抽出し、
  sitemap 未掲載カテゴリ（PS5ソフト・Switchソフト・Xbox 等）を静的リストで補完する。

商品フィルタ:
  .status-badge img の src に "status-new" を含む商品のみ取得（中古品は status-old.svg）。
  alt="new" は新品・中古両方に設定されているため src で判定する。

並列処理:
  ThreadPoolExecutor（MAX_WORKERS 並列）でリーフカテゴリを同時スキャン。
  results への書き込みは threading.Lock で保護する。

JAN 取得:
  .product-details a > h5:not(.product-details-name)
  テキストに "JAN:XXXX" 形式で格納されている。
"""

import re
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from scrapers.common import extract_jan, extract_price, merge_into_results
from scrapers.morimori.config import (
    SITE_ID, SITE_NAME, BASE_URL,
    REQUEST_DELAY_MIN, REQUEST_DELAY_MAX, PAGE_SIZE, MAX_WORKERS,
)


class MorimoriScraper(BaseScraper):
    site_id   = SITE_ID
    site_name = SITE_NAME

    def _sleep(self):
        """ランダムウェイトを挿入する（固定間隔パターンを回避）。"""
        time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))

    def _get_leaf_categories(self) -> list[str]:
        """sitemap.xml と静的補完リストを組み合わせて全カテゴリを取得する。

        sitemap.xml は PS5ソフト・Switchソフト・Xbox 等の一部カテゴリを掲載していない。
        また、4桁カテゴリページにはサブカテゴリリンクが存在しないため、
        直接プローブで確認済みの不掲載カテゴリを静的リストで補完する。
        """
        seen, result = set(), []

        def add_cat(cat):
            if cat not in seen:
                seen.add(cat)
                result.append(cat)

        # Step 1: sitemap.xml から取得（メイン）
        # 接続タイムアウト等で失敗する場合があるためリトライ処理を設ける
        resp = None
        for attempt in range(3):
            try:
                resp = self.get(BASE_URL + "/sitemap.xml")
                resp.raise_for_status()
                break
            except Exception as e:
                wait = 30 * (attempt + 1)
                if attempt < 2:
                    print(f"  [morimori] sitemap 取得失敗({attempt+1}/3): {e} → {wait}秒待機", flush=True)
                    time.sleep(wait)
                else:
                    print(f"  [morimori] sitemap 取得失敗(3/3): {e}", flush=True)
        if resp is not None:
            for cat in re.findall(r"/category/([^/]+)/product/\d+", resp.text):
                add_cat(cat)
        sitemap_count = len(result)

        # Step 2: sitemap に掲載されていない既知カテゴリを静的補完
        # 4桁カテゴリページにはサブカテゴリリンクが存在しないため、
        # 直接プローブで確認済みのカテゴリを静的に追加する
        SITEMAP_MISSING = [
            "0101002",  # PS5ソフト
            "0104002",  # Switchソフト
            "0104003",  # Switch Lite / Switch関連
            "0108001",  # Xbox Series X/S 本体
            "0108003",  # Xbox Series X/S アクセサリ
            "0109001",  # Xbox One 本体
            "0109003",  # Xbox One アクセサリ
            "0113001",  # Xbox Series S 本体（sitemap未掲載・プローブ確認済み2件）
            "0114",     # Meta Quest / VRヘッドセット（sitemap掲載だがキャンセルで消失、6件確認）
            "0115001",  # Steam Deck 本体（sitemap未掲載・プローブ確認済み7件）
        ]
        for cat in SITEMAP_MISSING:
            add_cat(cat)

        print(f"  sitemap: {sitemap_count}件, 補完: {len(result) - sitemap_count}件, 合計: {len(result)}件", flush=True)
        return result

    def _scan_category(self, cat_id: str, results: dict, lock: threading.Lock):
        """単一カテゴリの全ページをスキャンして results にマージする。

        PAGE_SIZE 件未満のページが最終ページ。
        lock で results への排他書き込みを保証する。

        Args:
            cat_id:  カテゴリ識別子（例: "iphone-15"）
            results: JAN をキーとする価格辞書（スレッド間共有）
            lock:    results への排他アクセス用ロック
        """
        # カテゴリ開始前に遅延を入れて同時アクセスによる 403 を回避
        self._sleep()
        page = 1
        while True:
            params = {"page": page} if page > 1 else {}
            # 接続失敗時は最大3回リトライ（待機時間を徐々に延ばす）
            resp = None
            for attempt in range(3):
                try:
                    resp = self.get(f"{BASE_URL}/category/{cat_id}", params=params)
                    resp.raise_for_status()
                    break
                except Exception as e:
                    wait = 30 * (attempt + 1)
                    print(f"  [morimori] {cat_id} page={page} 失敗({attempt+1}/3): {e} → {wait}秒待機", flush=True)
                    time.sleep(wait)
            if resp is None or not resp.ok:
                print(f"  [morimori] {cat_id} page={page} スキップ（リトライ上限）", flush=True)
                break

            soup  = BeautifulSoup(resp.text, "html.parser")
            items = soup.select(".product-item")
            if not items:
                break

            for item in items:
                # status-new.svg バッジのある商品のみ採用（中古品は status-old.svg だが alt も "new" のため src で判定）
                badge = item.select_one(".status-badge img")
                if not badge or "status-new" not in badge.get("src", ""):
                    continue

                # JAN は "JAN:XXXX" 形式の h5（商品名 h5 は .product-details-name クラスで除外）
                jan_el = item.select_one(".product-details a h5:not(.product-details-name)")
                jan = extract_jan(
                    jan_el.get_text(strip=True).replace("JAN:", "").strip()
                ) if jan_el else None
                if not jan:
                    continue
                # morimori は EAN-13（先頭 0 の 13 桁）を 12 桁で表示するため補完する
                if len(jan) == 12:
                    jan = "0" + jan

                # 通常買取価格（特別価格・キャンペーン価格は含まない）
                price_el = item.select_one(".price-normal-number h5")
                price = extract_price(price_el.get_text(strip=True)) if price_el else None
                if not price or price <= 0:
                    continue

                url_el  = item.select_one(".product-details a")
                url     = BASE_URL + url_el["href"] if url_el and url_el.get("href") else f"{BASE_URL}/category/{cat_id}"
                name_el = item.select_one("h5.product-details-name")
                name    = " ".join(name_el.get_text(separator=" ", strip=True).split()) if name_el else ""

                with lock:
                    merge_into_results(results, jan, name, price, url)

            print(f"  [morimori] {cat_id} page={page} ({len(items)}件)", flush=True)

            # PAGE_SIZE 件未満 = 最終ページ
            if len(items) < PAGE_SIZE:
                break
            page += 1
            self._sleep()

    def scrape(self) -> dict:
        """sitemap からリーフカテゴリを取得し、全カテゴリを並列スキャンして返す。"""
        results: dict = {}
        lock = threading.Lock()

        print("[morimori] sitemap からカテゴリ取得", flush=True)
        leaf_cats = self._get_leaf_categories()
        print(f"  leaf categories: {len(leaf_cats)}", flush=True)
        self._sleep()

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(self._scan_category, cat_id, results, lock): cat_id
                for cat_id in leaf_cats
            }
            for future in as_completed(futures):
                exc = future.exception()
                if exc:
                    cat_id = futures[future]
                    print(f"  [morimori] {cat_id} 例外: {exc}", flush=True)

        print(f"[morimori] 完了: {len(results)} JANs", flush=True)
        return results
