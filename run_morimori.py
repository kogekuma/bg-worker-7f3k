"""森森買取 leaf カテゴリ走査（シャード対応・cat99 除外）。

--shard N --total-shards M で leaf カテゴリを M 分割して担当分のみ取得する。
全商品集約カテゴリ cat99 は別ワークフロー run_morimori_cat99.py が担当するため
ここでは除外する。

シャード設計（Phase0 計測: 商品ありページの応答中央値 ~7.5秒）:
  - 通常カテゴリ: カテゴリ単位で stride 分割（cats[shard::total]）。多くは1ページ。
  - 大カテゴリ（BIG_CATEGORIES, 10ページ超）: 1シャードに偏ると14分窓を超えるため、
    ページ単位で全シャードに分散（shard k は page k+1, k+1+total, ...）。
  - SITEMAP_MISSING: 取りこぼし防止のため全シャードで必ず走査（各カテゴリは小さい）。

結果を morimori_shard_{N}.json として出力する（merge_morimori.py が増分マージ）。
"""

import argparse
import json
import threading
from datetime import datetime, timezone, timedelta

from scrapers.morimori import MorimoriScraper
from scrapers.morimori.scraper import AGGREGATE_CATEGORY, SITEMAP_MISSING

JST = timezone(timedelta(hours=9))

# 10ページ超の大カテゴリ（現行データ実測ベース）。1シャードに偏るとタイムアウトするため
# ページ単位で全シャードに分散する。新たに大きいカテゴリを見つけたらここに追加する。
BIG_CATEGORIES = {
    "0605002", "0801001", "0610005", "0610001", "0607003", "0208001",
    "0801008", "0104002", "0607004", "0303002", "0303001", "0401002",
    "0204002", "0610006", "0609001", "0605005", "0204001", "1401002",
    "0603001", "0304007",
}

parser = argparse.ArgumentParser()
parser.add_argument("--shard",        type=int, default=0, help="このジョブのシャード番号（0始まり）")
parser.add_argument("--total-shards", type=int, default=1, help="シャード総数")
args = parser.parse_args()

scraper = MorimoriScraper()

# sitemap から全カテゴリを発見し、cat99 を除外
all_cats   = [c for c in scraper._discover_categories() if c != AGGREGATE_CATEGORY]
missing_set = set(SITEMAP_MISSING)
big_set     = {c for c in BIG_CATEGORIES if c in all_cats}

# 通常カテゴリ（= 大カテゴリでも SITEMAP_MISSING でもない）を stride 分割
normal_cats = [c for c in all_cats if c not in big_set and c not in missing_set]
my_normal   = normal_cats[args.shard::args.total_shards]

print(
    f"[morimori leaf shard {args.shard}/{args.total_shards}] "
    f"通常 {len(my_normal)} / 大 {len(big_set)}(ページ分散) / SITEMAP {len(missing_set)}(全shard)",
    flush=True,
)

results: dict = {}
lock = threading.Lock()

try:
    # 1) 通常カテゴリ（担当分のみ・連続走査）
    for cat_id in my_normal:
        scraper._scan_category(cat_id, results, lock)

    # 2) SITEMAP_MISSING（全シャードで走査・取りこぼし防止）
    for cat_id in SITEMAP_MISSING:
        scraper._scan_category(cat_id, results, lock)

    # 3) 大カテゴリ（ページ単位で全シャードに分散）
    for cat_id in sorted(big_set):
        scraper._scan_category_pages(
            cat_id, results, lock,
            page_start=args.shard + 1, page_step=args.total_shards,
        )
except Exception as exc:
    # 403/429 ブロックや致命的エラー時は非ゼロ終了し、このシャードを失敗扱いにする。
    # → merge_morimori.py の増分マージが前回データを維持し、部分上書きを防ぐ。
    print(f"[morimori leaf shard {args.shard}] 中断: {exc}", flush=True)
    raise SystemExit(1)

print(f"[morimori leaf shard {args.shard}] 完了: {len(results)} JANs", flush=True)

output = {
    "updated": datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"),
    "shard":   args.shard,
    "scope":   "leaf",
    "count":   len(results),
    "items":   results,
}

filename = f"morimori_shard_{args.shard}.json"
with open(filename, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

print(f"→ {filename} に保存", flush=True)
