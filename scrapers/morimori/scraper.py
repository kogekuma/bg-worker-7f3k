"""森森買取（morimori-kaitori.jp）スクレイパー

GitHub Actions 上で実行（VPS IP ブロックを回避するため）。
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
        time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))

    def _get_leaf_categories(self) -> list[str]:
        resp = self.get(BASE_URL + "/sitemap.xml")
        all_cats = set(re.findall(r"/category/([^/]+)/product/\d+", resp.text))
        parents = {
            c for c in all_cats
            if any(o != c and o.startswith(c) for o in all_cats)
        }
        leaf_set = all_cats - parents
        leaf_set.discard("99")  # 全商品集約カテゴリ（288ページ）は他と重複するためスキップ
        seen, result = set(), []
        for cat in re.findall(r"/category/([^/]+)/product/\d+", resp.text):
            if cat not in seen and cat in leaf_set:
                seen.add(cat)
                result.append(cat)
        return result

    def _scan_category(self, cat_id: str, results: dict, lock: threading.Lock):
        self._sleep()
        page = 1
        while True:
            params = {"page": page} if page > 1 else {}
            try:
                resp = self.get(f"{BASE_URL}/category/{cat_id}", params=params)
                resp.raise_for_status()
            except Exception as e:
                print(f"  [morimori] {cat_id} page={page} 失敗: {e}", flush=True)
                break

            soup  = BeautifulSoup(resp.text, "html.parser")
            items = soup.select(".product-item")
            if not items:
                break

            for item in items:
                badge = item.select_one(".status-badge img")
                if not badge or badge.get("alt") != "new":
                    continue

                jan_el = item.select_one(".product-details a h5:not(.product-details-name)")
                jan = extract_jan(
                    jan_el.get_text(strip=True).replace("JAN:", "").strip()
                ) if jan_el else None
                if not jan:
                    continue

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

            if len(items) < PAGE_SIZE:
                break
            page += 1
            self._sleep()

    def scrape(self) -> dict:
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
                    print(f"  [morimori] {futures[future]} 例外: {exc}", flush=True)

        print(f"[morimori] 完了: {len(results)} JANs", flush=True)
        return results
