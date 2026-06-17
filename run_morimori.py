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

# SITEMAP_MISSING カテゴリはシャードに関わらず全シャードで必ず処理する
# (並走するスケジュール実行で一部シャードがキャンセルされても取得漏れを防ぐ)
SITEMAP_MISSING = [
    "0101001",  # PS5本体（シャードキャンセル時の消失防止）
    "0101002",  # PS5ソフト
    "0104002",  # Switchソフト
    "0104003",  # Switch Lite / Switch関連
    "0108001",  # Xbox Series X/S 本体
    "0108003",  # Xbox Series X/S アクセサリ
    "0109001",  # Xbox One 本体
    "0109003",  # Xbox One アクセサリ
]
# シャード担当分 + 全SITEMAP_MISSINGカテゴリ（重複はsetで排除）
my_cats_set  = set(leaf_cats[args.shard::args.total_shards])
extra_cats   = [c for c in SITEMAP_MISSING if c not in my_cats_set]
my_cats      = leaf_cats[args.shard::args.total_shards] + extra_cats

print(f"[morimori shard {args.shard}/{args.total_shards}] {len(my_cats)} カテゴリ担当 (SITEMAP追加: {len(extra_cats)}件)", flush=True)

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
