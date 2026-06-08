"""モバイル一番（mobile-ichiban.com）スクレイパー

サイト構造（POST ベースのページネーション）:
  - 1ページ目: POST /        form データでカテゴリを指定
  - 2ページ目以降: POST /G01_ProdutShow/Index/{page}  同じ form データ
  - ページ数: #bootstrappager の data-pagecount 属性
"""

import hashlib
import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper
from scrapers.common import extract_jan, extract_price, merge_into_results
from scrapers.mobile_ichiban.config import (
    SITE_ID, SITE_NAME, BASE_URL,
    REQUEST_DELAY_MIN, REQUEST_DELAY_MAX, MAX_WORKERS, CAT_IDS,
)

# 接続失敗時のリトライ設定
CONNECT_RETRY = 3          # 最大リトライ回数
RETRY_INTERVAL = 30        # リトライ間隔（秒）


def _pseudo_jan(name: str) -> str:
    """JAN なし商品に対し商品名から固定擬似 JAN を生成する（13桁数字、先頭 "00"）。"""
    h = int(hashlib.md5(name.lower().strip().encode()).hexdigest(), 16) % 10 ** 11
    return f"00{h:011d}"


def _parse_color_deduction(remarks: str) -> int:
    """色別減額テキストから最大減額額（正の整数）を返す。"""
    nums = re.findall(r"-\s*(\d[\d,]*)", remarks)
    if not nums:
        return 0
    return max(int(n.replace(",", "")) for n in nums)


class MobileIchibanScraper(BaseScraper):
    site_id   = SITE_ID
    site_name = SITE_NAME

    def _sleep(self):
        time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))

    def _get_categories(self) -> list[tuple[str, str]]:
        # ConnectTimeout が断続的に発生するため、リトライを実装する
        for attempt in range(CONNECT_RETRY):
            try:
                resp = self.get(BASE_URL + "/", timeout=30)
                soup = BeautifulSoup(resp.text, "html.parser")
                cats = []
                for el in soup.select("a.ul-max-a"):
                    if el.get("id") in CAT_IDS:
                        cats.append((el["id"], el.get_text(strip=True)))
                return cats
            except Exception as e:
                print(f"[mobile_ichiban] カテゴリ取得失敗（試行{attempt+1}/{CONNECT_RETRY}）: {e}", flush=True)
                if attempt < CONNECT_RETRY - 1:
                    print(f"[mobile_ichiban] {RETRY_INTERVAL}秒後にリトライ...", flush=True)
                    time.sleep(RETRY_INTERVAL)
        return []

    def _parse_page(self, soup, cat_id: str) -> list[tuple[str, str, int, str]]:
        items = []
        for price_el in soup.select("[id^=NewPrice_]"):
            prod_id = price_el["id"].replace("NewPrice_", "")

            new_txt = price_el.get_text(strip=True)
            old_el  = soup.select_one(f"#OldPrice_{prod_id}")
            old_txt = old_el.get_text(strip=True) if old_el else ""
            price_txt = new_txt if new_txt else old_txt
            price = extract_price(price_txt)
            if not price or price <= 0:
                continue

            img = soup.select_one(f"#Img_{prod_id}")
            card = img
            while card and (card.name != "div" or "card" not in (card.get("class") or [])):
                card = card.parent

            if card:
                remarks_el = card.select_one("small.my-prod-remarks")
                if remarks_el:
                    deduction = _parse_color_deduction(remarks_el.get_text(strip=True))
                    if deduction > 0:
                        price = max(price - deduction, 0)

                name_el = card.select_one("label.hideText")
                name = name_el.get("title", "").strip() if name_el else ""

                jan_el  = card.select_one("small.text-muted")
                jan_raw = jan_el.get_text(strip=True) if jan_el else ""
                jan_str = re.sub(r"[^0-9]", "", jan_raw.upper().replace("JAN", "").replace(":", ""))
                jan = extract_jan(jan_str)

                if not jan and name:
                    jan = _pseudo_jan(name)
            else:
                continue

            if not jan or not name or not price:
                continue

            url = f"{BASE_URL}/Prod/{cat_id}"
            items.append((jan, name, price, url))
        return items

    def _scan_category(self, cat_id: str, cat_name: str,
                       results: dict, lock: threading.Lock):
        base_data = {
            "g01Search": "", "g01tagLevel": "1",
            "g01tagCodeLevel1": cat_id, "g01tagCodeLevel2": "",
            "g01tagCodeLevel3": "", "g01tagNameLevel1": cat_name,
            "g01tagNameLevel2": "", "g01tagNameLevel3": "",
            "LeftTagJson": "", "TagJson": "", "g01ListOrImg": "1", "idCustom": "",
        }

        try:
            resp = self.post(BASE_URL + "/", data=base_data, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            print(f"  [mobile_ichiban] cat={cat_id} page=1 失敗: {e}", flush=True)
            return

        soup = BeautifulSoup(resp.text, "html.parser")
        pager = soup.select_one("#bootstrappager")
        max_page = int(pager.get("data-pagecount", 1)) if pager else 1

        items = self._parse_page(soup, cat_id)
        with lock:
            for jan, name, price, url in items:
                merge_into_results(results, jan, name, price, url)
        print(f"  [mobile_ichiban] cat={cat_id} page=1/{max_page} ({len(items)}件)", flush=True)
        self._sleep()

        for page in range(2, max_page + 1):
            try:
                resp = self.post(
                    f"{BASE_URL}/G01_ProdutShow/Index/{page}",
                    data=base_data,
                    timeout=30,
                )
                resp.raise_for_status()
            except Exception as e:
                print(f"  [mobile_ichiban] cat={cat_id} page={page} 失敗: {e}", flush=True)
                self._sleep()
                continue

            items = self._parse_page(BeautifulSoup(resp.text, "html.parser"), cat_id)
            with lock:
                for jan, name, price, url in items:
                    merge_into_results(results, jan, name, price, url)
            print(f"  [mobile_ichiban] cat={cat_id} page={page}/{max_page} ({len(items)}件)", flush=True)
            self._sleep()

    def scrape(self) -> dict:
        results: dict = {}
        lock = threading.Lock()

        cats = self._get_categories()
        if not cats:
            print(f"[mobile_ichiban] カテゴリ取得失敗（スキップ）", flush=True)
            return results
        print(f"[mobile_ichiban] カテゴリ数: {len(cats)}", flush=True)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(self._scan_category, cat_id, cat_name, results, lock): cat_id
                for cat_id, cat_name in cats
            }
            for future in as_completed(futures):
                exc = future.exception()
                if exc:
                    print(f"  [mobile_ichiban] cat={futures[future]} 例外: {exc}", flush=True)

        print(f"[mobile_ichiban] 完了: {len(results)} JANs", flush=True)
        return results