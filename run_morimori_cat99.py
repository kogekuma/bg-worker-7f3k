"""森森買取 cat99（全商品集約カテゴリ）走査・ページ分散版。

cat99 は「家電・その他」の受け皿カテゴリ（289ページ・約2881件・新品率88%）で、
leaf カテゴリ群とは別商品群（約2529件）を含む。1シャードで全ページを直列走査すると
14分のタイムアウト窓を超えるため、ページ単位で全シャードに分散する。

  --shard k --total-shards M → page k+1, k+1+M, k+1+2M, ... を担当（商品0件まで）。

leaf 走査（run_morimori.py）とは別ワークフロー・別スケジュールで動かし、
失敗ドメインを分離する。結果は morimori_cat99_shard_{N}.json として出力。
"""

import argparse
import json
import threading
from datetime import datetime, timezone, timedelta

from scrapers.morimori import MorimoriScraper
from scrapers.morimori.scraper import AGGREGATE_CATEGORY, MorimoriBlockedError

JST = timezone(timedelta(hours=9))

parser = argparse.ArgumentParser()
parser.add_argument("--shard",        type=int, default=0, help="このジョブのシャード番号（0始まり）")
parser.add_argument("--total-shards", type=int, default=1, help="シャード総数")
args = parser.parse_args()

scraper = MorimoriScraper()

print(
    f"[morimori cat99 shard {args.shard}/{args.total_shards}] "
    f"page {args.shard + 1}, +{args.total_shards} ずつ走査",
    flush=True,
)

results: dict = {}
lock = threading.Lock()
blocked = False

try:
    scraper._scan_category_pages(
        AGGREGATE_CATEGORY, results, lock,
        page_start=args.shard + 1, page_step=args.total_shards,
    )
    complete = True
except MorimoriBlockedError as exc:
    # ブロック時は非ゼロ終了。merge 側は complete=False を見て cat99 を上書きしない。
    print(f"[morimori cat99 shard {args.shard}] ブロック中断: {exc}", flush=True)
    raise SystemExit(1)
except Exception as exc:
    print(f"[morimori cat99 shard {args.shard}] 中断: {exc}", flush=True)
    raise SystemExit(1)

print(f"[morimori cat99 shard {args.shard}] 完了: {len(results)} JANs", flush=True)

output = {
    "updated":  datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"),
    "shard":    args.shard,
    "scope":    "cat99",
    "complete": complete,   # この page-stride を最後（0件ページ）まで走査できたか
    "count":    len(results),
    "items":    results,
}

filename = f"morimori_cat99_shard_{args.shard}.json"
with open(filename, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

print(f"→ {filename} に保存", flush=True)
