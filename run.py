"""モバイル一番スクレイパー実行スクリプト。

結果を mobile_ichiban.json として出力する。
GitHub Actions から Scanner リポジトリの docs/data/ に push される。
"""

import json
import sys
from datetime import datetime, timezone, timedelta

from scrapers.mobile_ichiban import MobileIchibanScraper

JST = timezone(timedelta(hours=9))

scraper = MobileIchibanScraper()
data = scraper.scrape()

if not data:
    print("取得件数が0件のため mobile_ichiban.json を更新しません（接続失敗の可能性）", flush=True)
    sys.exit(0)

# ページの取得失敗が多いときは書き出さず run を赤にする。
# 2026-10-08〜17 にページャの URL 仕様変更で2ページ目以降が全部 404 になり、1ページ目だけの
# 140件（本来 2,620件）を「成功」として書き続けた。updated が進むので鮮度監視でも気づけなかった。
# 赤にすれば updated が止まり、約2時間で VPS の鮮度監視も通知する。
MAX_PAGE_FAIL_RATIO = 0.2
total, failed = scraper.pages_total, scraper.pages_failed
if total and failed / total > MAX_PAGE_FAIL_RATIO:
    print(f"::error::[mobile_ichiban] ページ取得失敗 {failed}/{total} が多すぎるため更新しません"
          f"（サイト側の仕様変更を疑ってください）", flush=True)
    sys.exit(1)

output = {
    "updated": datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"),
    "count": len(data),
    "items": data,
}

with open("mobile_ichiban.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

print(f"完了: {len(data)} JANs", flush=True)