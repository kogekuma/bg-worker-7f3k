"""買取商店（kaitorishouten-co.jp）スクレイパー

スクレイピング戦略（6フェーズ）:
  Phase 1: AJAX エンドポイント（keitai・kaden）
    - ベースページでセッション確立 → X-Requested-With ヘッダー付きで AJAX 取得
    - 優先データソース: AJAX で取得した JAN は以降フェーズで上書きしない
    - この AJAX リクエストで取得した Cookie（AWSALB 等）が Phase 5・6 に必要
    - 直列（self.session に Cookie を蓄積）。完了後に Cookie をスナップショットして
      以降の並列フェーズは requests.get に cookies として渡す（Session は並列共有非対応）

  Phase 5: kaden カテゴリページ（ゲームソフト・カード等 AJAX 未収録分・約1000件の独立ソース）
  Phase 6: nitiyouhin カテゴリページ（ウィスキー・日本酒・ワイン等）
  Phase 3: category/3 全 ID（最大商品ソース）
  Phase 4: category/4 keitai サブカテゴリ

高速化（2026-07-02・kaden/morimori と同パターン）:
  従来は Phase 5 が 1 並列＋2.5秒遅延で約30分かかり全体47分だった。
  「サイト全体で共有するグローバルレート制限（約1req/秒）＋各フェーズ並列化＋
   403/429 即中断」に統一。GitHub Actions（run毎に新規IP）で実行するため、
   VPS固定IP時代の 1 並列は過剰保守だった。

HTML 構造（2種類）:
  カードレイアウト（AJAX _new + category/3）:
    span.product-code-default "JAN:" の次の span が JAN 値
    コンテナ: <form data-calc-url> / 商品名: h4.item-title / 価格: div.item-price.plain-price
  テーブルレイアウト（kaden タグページ等）:
    コンテナ: <tr class="price_list_item"> / td[1]=商品名+JAN / 価格: div.item-price.plain-price
"""

import random
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper, CHROME_HEADERS
from scrapers.common import extract_jan, extract_price, merge_into_results
from scrapers.kaitorishouten.config import (
    SITE_ID, SITE_NAME, BASE_URL, AJAX_CATEGORIES, AJAX_DELAY,
    GLOBAL_MIN_INTERVAL_MIN, GLOBAL_MIN_INTERVAL_MAX,
    MAX_WORKERS, PHASE5_WORKERS, PHASE6_WORKERS,
)

# WAF ブロックを示すステータス（即中断し、リトライしない）
BLOCK_STATUS_CODES = {403, 429}


class KaitorishoutenBlockedError(RuntimeError):
    """403/429 検知時に部分データで上書きしないための中断例外。"""


class KaitorishoutenScraper(BaseScraper):
    site_id   = SITE_ID
    site_name = SITE_NAME

    def __init__(self):
        super().__init__()
        self._rate_lock = threading.Lock()       # グローバルレート制限用
        self._last_request_at = 0.0
        self._merge_lock = threading.Lock()       # 共有 results への排他書き込み用
        self._abort = threading.Event()           # ブロック検知で全フェーズ中断
        self._cookies: dict = {}                  # Phase 1 で確立した Cookie のスナップショット

    def _wait_global_rate_limit(self) -> None:
        """全スレッド共有で、任意の2リクエストの開始間隔を空ける（総リクエスト速度を抑制）。"""
        with self._rate_lock:
            now = time.time()
            if self._last_request_at:
                interval = random.uniform(GLOBAL_MIN_INTERVAL_MIN, GLOBAL_MIN_INTERVAL_MAX)
                wait = self._last_request_at + interval - now
                if wait > 0:
                    time.sleep(wait)
                    now = time.time()
            self._last_request_at = now

    def _session_get(self, url: str, **kwargs):
        """Phase 1 用（self.session で Cookie を蓄積）。レート制限＋ブロック検知付き。"""
        if self._abort.is_set():
            raise KaitorishoutenBlockedError("kaitorishouten aborted")
        self._wait_global_rate_limit()
        resp = self.get(url, **kwargs)
        if resp.status_code in BLOCK_STATUS_CODES:
            self._abort.set()
            raise KaitorishoutenBlockedError(f"blocked: HTTP {resp.status_code} {url}")
        return resp

    def _fetch(self, url: str, params: dict | None = None, referer: str | None = None):
        """並列フェーズ用のレート制限つき GET（requests.get・Cookie スナップショット使用）。

        403/429 は即中断、接続エラー/5xx は最大3回リトライ、404 は None（カテゴリ終了扱い）。
        requests.get を直接使う（BaseScraper.session はスレッド共有非対応のため）。
        """
        headers = dict(CHROME_HEADERS)
        if referer:
            headers["Referer"] = referer
        # read timeout / 一時エラーは軽くリトライ（1回・5秒）。timeout は 15秒。
        # 長い 10/30/60秒×3 はサーバ遅延時に1ページ190秒を食い潰し全体を遅くするため短縮。
        last_error = None
        for attempt in range(2):
            if self._abort.is_set():
                raise KaitorishoutenBlockedError("kaitorishouten aborted")
            self._wait_global_rate_limit()
            try:
                resp = requests.get(
                    url, params=params, headers=headers, cookies=self._cookies, timeout=15
                )
            except Exception as exc:
                last_error = exc
                if attempt == 1:
                    break
                time.sleep(5 + random.uniform(0, 2))
                continue

            if resp.status_code in BLOCK_STATUS_CODES:
                self._abort.set()
                raise KaitorishoutenBlockedError(f"blocked: HTTP {resp.status_code} {url}")
            if resp.status_code == 404:
                return None
            if resp.status_code >= 500:
                last_error = Exception(f"HTTP {resp.status_code}")
                if attempt == 1:
                    break
                time.sleep(5 + random.uniform(0, 2))
                continue
            if resp.status_code != 200:
                return None
            return resp
        raise last_error if last_error else Exception("fetch failed")

    def _get_sitemap_ids(self) -> dict:
        """sitemap.xml から category/2・/3・/4 の ID 一覧を取得する。"""
        try:
            r = self._fetch(BASE_URL + "/sitemap.xml")
        except KaitorishoutenBlockedError:
            raise
        except Exception as e:
            print(f"  [kaitorishouten] sitemap.xml 取得失敗: {e}", flush=True)
            return {"cat2": [], "cat3": [], "cat4": []}
        if r is None:
            return {"cat2": [], "cat3": [], "cat4": []}
        ids = {}
        for key, pat in [("cat2", "/category/2/"), ("cat3", "/category/3/"), ("cat4", "/category/4/")]:
            ids[key] = sorted(set(int(x) for x in re.findall(rf"{re.escape(pat)}(\d+)", r.text)))
        return ids

    def _extract_jans(self, soup) -> list[tuple[str, str, int | None]]:
        """カード・テーブル両レイアウト対応で (jan, name, price) リストを返す。"""
        items = []
        spans = soup.select("span.product-code-default")
        for i, s in enumerate(spans):
            if s.get_text(strip=True) != "JAN:" or i + 1 >= len(spans):
                continue
            jan = extract_jan(spans[i + 1].get_text(strip=True))
            if not jan:
                continue

            # 最近傍の <tr> または <form> をコンテナとして特定
            container = None
            for ancestor in spans[i].parents:
                if ancestor.name in ("tr", "form"):
                    container = ancestor
                    break

            name, price, price_el = "", None, None
            if container:
                if container.name == "tr":
                    # テーブルレイアウト: JAN span の親 td から商品名を取得
                    name_td = None
                    for p in spans[i].parents:
                        if p.name == "td":
                            name_td = p
                            break
                    if name_td:
                        lines = [
                            ln.strip()
                            for ln in name_td.get_text(separator="\n").split("\n")
                            if ln.strip()
                        ]
                        name = " ".join(
                            ln for ln in lines
                            if not ln.startswith("JAN") and not re.fullmatch(r"\d+", ln)
                        )[:100]
                    price_el = container.select_one("div.item-price.plain-price")
                else:
                    # カードレイアウト: h4.item-title に商品名
                    title_el = container.select_one("h4.item-title")
                    if title_el:
                        name = title_el.get_text(strip=True)
                    price_el = container.select_one("div.item-price.plain-price")
                if price_el:
                    price = extract_price(price_el.get_text(strip=True))
            items.append((jan, name, price))
        return items

    def _get_category_ids_from_nav(self, page_path: str, referer: str) -> list[int]:
        """指定ページのナビ a.do-product-list[data-category] から list_category ID 一覧を取得する。"""
        try:
            resp = self._fetch(BASE_URL + page_path, referer=referer)
        except KaitorishoutenBlockedError:
            raise
        except Exception as e:
            print(f"  [kaitorishouten] {page_path} category ID 取得失敗: {e}", flush=True)
            return []
        if resp is None:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        ids: set[int] = set()
        for a in soup.select("a.do-product-list[data-category]"):
            try:
                ids.add(int(a["data-category"]))
            except (ValueError, KeyError):
                pass
        return sorted(ids)

    def _scan_ajax(self, base_path: str, ajax_path: str, results: dict):
        """_new AJAX エンドポイントの全ページをスキャンする（Phase 1・直列・優先データソース）。"""
        url_base = BASE_URL + base_path
        url_ajax = BASE_URL + ajax_path
        try:
            self._session_get(url_base)
        except KaitorishoutenBlockedError:
            raise
        except Exception as e:
            print(f"  [kaitorishouten] {base_path} base failed: {e}")
            time.sleep(AJAX_DELAY)
            return

        self.session.headers.update({"X-Requested-With": "XMLHttpRequest", "Referer": url_base})
        page = 1
        while not self._abort.is_set():
            try:
                resp = self._session_get(url_ajax, params={"pageno": page})
                resp.raise_for_status()
            except KaitorishoutenBlockedError:
                raise
            except Exception as e:
                print(f"  [kaitorishouten] {ajax_path} page={page} failed: {e}")
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            # form[data-calc-url] が存在しなければ商品ゼロ = 最終ページを超えた
            if not soup.select("form[data-calc-url]"):
                break

            for jan, name, price in self._extract_jans(soup):
                if price:
                    with self._merge_lock:
                        merge_into_results(results, jan, name, price, url_base)
            print(f"  [kaitorishouten] {base_path} ajax page={page}", flush=True)
            page += 1

    def _scan_category(self, cat_path: str, results: dict, referer: str, force: bool = False):
        """カテゴリページを全ページスキャンして results にマージする（並列・レート制限つき）。

        ページ数は 1ページ目のページネーションリンクから動的に取得する。
        書き込みは _merge_lock で保護。403/429 は KaitorishoutenBlockedError を送出。
        """
        url = BASE_URL + cat_path
        page, max_page = 1, 1
        while not self._abort.is_set():
            try:
                resp = self._fetch(url, params={"pageno": page} if page > 1 else {}, referer=referer)
            except KaitorishoutenBlockedError:
                raise
            except Exception as e:
                print(f"  [kaitorishouten] {cat_path} page={page} failed: {e}")
                break
            if resp is None:
                break  # 404 = カテゴリ廃止

            soup = BeautifulSoup(resp.text, "html.parser")
            if page == 1:
                # category/3 は a.page-link、list_category は javascript:goto_page('N') を使う
                nums = [
                    int(a.get_text(strip=True))
                    for a in soup.select("a.page-link")
                    if a.get_text(strip=True).isdigit()
                ]
                if not nums:
                    for a in soup.select("a[href*='goto_page']"):
                        m = re.search(r"goto_page\('(\d+)'\)", a.get("href", ""))
                        if m:
                            nums.append(int(m.group(1)))
                max_page = max(nums) if nums else 1

            for jan, name, price in self._extract_jans(soup):
                if price:
                    with self._merge_lock:
                        merge_into_results(results, jan, name, price, url, force=force)

            if page >= max_page:
                break
            page += 1

    def _run_phase(self, cat_paths: list[str], referer: str, workers: int, force: bool,
                   results: dict, label: str):
        """カテゴリ群を並列スキャンする共通処理。ブロック時は例外を伝播させる。"""
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._scan_category, path, results, referer, force): path
                for path in cat_paths
            }
            for future in as_completed(futures):
                try:
                    future.result()
                except KaitorishoutenBlockedError:
                    self._abort.set()
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise
                except Exception as exc:
                    print(f"  [kaitorishouten] {label} {futures[future]} 例外: {exc}", flush=True)

    def scrape(self) -> dict:
        """6フェーズでスキャンして JAN → 価格情報の辞書を返す。"""
        results: dict = {}

        try:
            # ── Phase 1: AJAX（keitai・kaden、直列、優先データソース）─────
            print("[kaitorishouten] Phase 1: AJAX endpoints", flush=True)
            for base_path, ajax_path in AJAX_CATEGORIES:
                self._scan_ajax(base_path, ajax_path, results)
            print(f"  AJAX total: {len(results)} JANs", flush=True)

            # Phase 1 で確立した Cookie（AWSALB 等）をスナップショット → 以降の並列 GET で使う
            self._cookies = requests.utils.dict_from_cookiejar(self.session.cookies)
            self.session.headers.pop("X-Requested-With", None)

            # ── Phase 5: kaden list_category（AJAX 未収録のゲームソフト・カード等）──
            cat_ids = self._get_category_ids_from_nav("/kaden", BASE_URL + "/kaden")
            print(f"[kaitorishouten] Phase 5: kaden list_category ({len(cat_ids)} categories)", flush=True)
            if cat_ids:
                self._run_phase(
                    [f"/products/2/list_category/{cid}" for cid in cat_ids],
                    referer=BASE_URL + "/kaden", workers=PHASE5_WORKERS, force=False,
                    results=results, label="list_category",
                )
            print(f"  Phase 5 after: {len(results)} JANs", flush=True)

            # ── Phase 6: nitiyouhin list_category（酒類等）──
            niti_ids = self._get_category_ids_from_nav("/nitiyouhin", BASE_URL + "/nitiyouhin")
            print(f"[kaitorishouten] Phase 6: nitiyouhin list_category ({len(niti_ids)} categories)", flush=True)
            if niti_ids:
                self._run_phase(
                    [f"/products/3/list_category/{cid}" for cid in niti_ids],
                    referer=BASE_URL + "/nitiyouhin", workers=PHASE6_WORKERS, force=False,
                    results=results, label="nitiyouhin list_category",
                )
            print(f"  Phase 6 after: {len(results)} JANs", flush=True)

            # sitemap.xml からカテゴリ ID を取得
            sm = self._get_sitemap_ids()
            print(f"[kaitorishouten] sitemap: cat2={len(sm['cat2'])} cat3={len(sm['cat3'])} cat4={len(sm['cat4'])}", flush=True)

            # ── Phase 3: category/3（最大 JAN ソース）──
            print("[kaitorishouten] Phase 3: category/3", flush=True)
            self._run_phase(
                [f"/category/3/{cid}" for cid in sm["cat3"]],
                referer=BASE_URL + "/nitiyouhin", workers=MAX_WORKERS, force=True,
                results=results, label="cat3",
            )

            # ── Phase 4: category/4（keitai サブ）──
            print("[kaitorishouten] Phase 4: category/4", flush=True)
            self._run_phase(
                [f"/category/4/{cid}" for cid in sm["cat4"]],
                referer=BASE_URL + "/keitai", workers=MAX_WORKERS, force=True,
                results=results, label="cat4",
            )
        except KaitorishoutenBlockedError as exc:
            # WAF ブロック → 部分データで上書きしないよう例外を送出（run_all/GitHub 側で前回データ保持）
            print(f"[kaitorishouten] ブロック中断: {exc}", flush=True)
            raise

        # category/2 (kaden) は AJAX kaden と同一セットのためスキャン不要
        print(f"[kaitorishouten] done: {len(results)} JANs", flush=True)
        return results
