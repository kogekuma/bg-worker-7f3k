"""スニダン参考価格取得スクリプト（bg-worker-7f3k 版）

scrapers/snkrdunk/ を実行して snkrdunk.json を生成する。
GitHub Actions から定期実行して Scanner リポジトリに push する。
"""

import json
import sys
from datetime import datetime, timezone, timedelta

from scrapers.snkrdunk import SnkrdunkScraper

JST = timezone(timedelta(hours=9))
OUTPUT_PATH = "snkrdunk.json"


def main():
    scraper = SnkrdunkScraper(cache_path=OUTPUT_PATH)
    items = scraper.scrape()

    if not items:
        print("取得件数が0件のため snkrdunk.json を更新しません（レー〈リミットの可能性）", flush=True)
        sys.exit(0)

    output = {
        "updated": datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"),
        "count":   len(items),
        "items":   items,
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    print(f"完了: {len(items)} 件 → {OUTPUT_PATH}", flush=True)


if __name__ == "__main__":
    main()