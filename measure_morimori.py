"""morimori レイテンシ計測 dry-run（Phase 0・書き込みなし）。

目的:
  GitHub Actions ランナー（新規 IP）から morimori-kaitori.jp の
  「商品ありページ」の応答レイテンシ中央値を計測し、leaf 走査の
  シャード数・大カテゴリ分割の要否を判定する。

  ローカル IP では当該サイトへの連続アクセスでソフトスロットリングが
  かかり中央値 ~7 秒まで膨らんだ。Actions の新規 IP で中央値が 1〜2 秒台
  に戻れば「簡素構成（leaf 10 シャード）」、5 秒以上なら「堅牢構成
  （leaf 20 シャード＋大カテゴリ page task 分割）」を採る。

計測対象:
  cat 99（家電・その他の受け皿、289 ページの巨大カテゴリ）の
  商品ありページを直列で取得し、各リクエストの所要時間を測る。
  データの保存・マージは一切行わない。
"""

import statistics
import time

import requests
from bs4 import BeautifulSoup

from scrapers.base import CHROME_HEADERS

BASE_URL = "https://www.morimori-kaitori.jp"
# cat 99 は ~289 ページあるため、先頭 18 ページ（すべて商品あり）を計測する
PAGES = list(range(1, 19))
# リクエスト間の最小ギャップ（実走に近い間隔。計測自体が連打にならないよう緩める）
GAP_SEC = 1.0


def main():
    session = requests.Session()

    elapsed_list = []
    print("[measure] cat99 商品ありページのレイテンシ計測開始", flush=True)
    for i, page in enumerate(PAGES):
        params = {} if page == 1 else {"page": page}
        t0 = time.time()
        try:
            resp = session.get(
                f"{BASE_URL}/category/99", params=params, headers=CHROME_HEADERS, timeout=30
            )
            elapsed = time.time() - t0
        except Exception as exc:
            print(f"  page={page}: ERROR {exc}", flush=True)
            continue

        n_items = len(BeautifulSoup(resp.text, "html.parser").select(".product-item"))
        size_kb = len(resp.content) / 1024
        # 商品ありページのみ集計（空ページは判定対象外）
        if n_items > 0:
            elapsed_list.append(elapsed)
        print(
            f"  page={page:>3}: HTTP {resp.status_code} "
            f"elapsed={elapsed:5.2f}s size={size_kb:6.1f}KB items={n_items}",
            flush=True,
        )
        if i < len(PAGES) - 1:
            time.sleep(GAP_SEC)

    if not elapsed_list:
        print("[measure] 商品ありページを取得できませんでした", flush=True)
        return

    med = statistics.median(elapsed_list)
    print("[measure] === 結果 ===", flush=True)
    print(
        f"[measure] 商品ありページ n={len(elapsed_list)} "
        f"min={min(elapsed_list):.2f}s median={med:.2f}s max={max(elapsed_list):.2f}s",
        flush=True,
    )
    verdict = "簡素構成（leaf 10 シャードで可）" if med <= 2.0 else (
        "中間（leaf 15 シャード検討）" if med < 5.0 else "堅牢構成（leaf 20 シャード＋大カテゴリ分割）"
    )
    print(f"[measure] 判定: median={med:.2f}s → {verdict}", flush=True)


if __name__ == "__main__":
    main()
