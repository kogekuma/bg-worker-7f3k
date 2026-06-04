"""森森買取スクレイパー実行スクリプト（シャード対応版）。

--shard N --total N で全カテゴリを N 分割して担当分のみ取得する。
GitHub Actions matrix で 5 並列実行し IP を分散させる。

結果を morimori_shard_{N}.json として出力。
"""

import argparse
import json
import re
from datetime import datetime, timezone, timedelta

from scrapers.morimori import MorimoriScraper

JST = timezone(timedelta(hours=9))

parser = argparse.ArgumentParser()
parser.add_argument("--shard",        type=int, default=0, help="このジョブのシャード番号（0始まり）")
parser.add_argument("--total-shards", type=int, default=1, help="シャード総数")
args = parser.parse_args()

scraper = MorimoriScraper()

# カテゴリを取得してシャード分割
leaf_cats = scraper._get_leaf_categories()
my_cats   = leaf_cats[args.shard::args.total_shards]  # 担当カテゴリ（例: 0,5,10,15...）

print(f"[morimori shard {args.shard}/{args.total_shards}] {len(my_cats)} カテゴリ担当", flush=True)

# シャード内のカテゴリのみスクレイピング（1並列・順番に）
import threading
results = {}
lock    = threading.Lock()
for cat_id in my_cats:
    scraper._scan_category(cat_id, results, lock)

print(f"[morimori shard {args.shard}] 完了: {len(results)} JANs", flush=True)

output = {
    "updated": datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"),
    "shard":   args.shard,
    "count":   len(results),
    "items":   results,
}

filename = f"morimori_shard_{args.shard}.json"
with open(filename, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

print(f"→ {filename} に保存", flush=True)
