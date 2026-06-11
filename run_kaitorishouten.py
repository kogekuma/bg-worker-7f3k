"""買取商店スクレイパー実行スクリプト。

結果を kaitorishouten.json として出力する。
GitHub Actions から Scanner リポジトリの docs/data/ に push される。
"""

import json
import sys
from datetime import datetime, timezone, timedelta

from scrapers.kaitorishouten import KaitorishoutenScraper

JST = timezone(timedelta(hours=9))

scraper = KaitorishoutenScraper()
data = scraper.scrape()

if not data:
    print("取得件数が0件のため kaitorishouten.json を更新しません（接続失敗の可能性）", flush=True)
    sys.exit(0)

output = {
    "updated": datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"),
    "count": len(data),
    "items": data,
}

with open("kaitorishouten.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

print(f"完了: {len(data)} JANs", flush=True)
