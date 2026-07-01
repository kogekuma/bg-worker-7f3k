"""森森買取 leaf カテゴリ走査（シャード対応・cat99 除外）。

--shard N --total-shards M で leaf カテゴリを M 分割して担当分のみ取得する。
全商品集約カテゴリ cat99 は別ワークフロー run_morimori_cat99.py が担当するため
ここでは除外する。

シャード設計（Phase0 計測: 商品ありページの応答中央値 ~7.5秒）:
  - 通常カテゴリ: カテゴリ単位で stride 分割（cats[shard::total]）。多くは1ページ。
  - 大カテゴリ（BIG_CATEGORIES, 12ページ超）: 1シャードに偏ると14分窓を超えるため、
    ページ単位で全シャードに分散（shard k は page k+1, k+1+total, ...）。
  - SITEMAP_MISSING: 取りこぼし防止のため全シャードで必ず走査（各カテゴリは小さい）。

  leaf 全体は約2708ページ（商品はほぼ全て新品・複数カテゴリに重複掲載）で、直列だと
  1ページ ~8秒律速で20シャードでも14分を超える。シャード内を LEAF_WORKERS 並列にすると、
  グローバルレート制限（2-3秒/開始間隔）が律速になり実効 ~4秒/ページに短縮される
  （latency 律速 → レート律速）。結果への書き込みは lock、リクエスト間隔は
  scraper 側の _rate_lock で保護されるためスレッドセーフ。

結果を morimori_shard_{N}.json として出力する（merge_morimori.py が増分マージ）。
"""

import argparse
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

from scrapers.morimori import MorimoriScraper
from scrapers.morimori.scraper import AGGREGATE_CATEGORY, MorimoriBlockedError, SITEMAP_MISSING

JST = timezone(timedelta(hours=9))

# シャード内の並列ワーカー数。グローバルレート制限（2-3秒）があるため 403 誘発は
# 抑えられる（旧来の 5 並列・レート制限なしとは異なる）。まず 3 で運用する。
LEAF_WORKERS = 3

# leaf から除外するカテゴリ。
#   99 = 全商品集約（別ワークフロー run_morimori_cat99.py が担当）
#   05 = 冗長な集約カテゴリ（196ページ。サンプル新品100%が7桁leafでカバー済み＝除外可）
EXCLUDE_FROM_LEAF = {AGGREGATE_CATEGORY, "05"}

# 12ページ超の大カテゴリ（2026-07-01 実ログ実測ベース。中古込みの実ページ数）。
# 1シャードに偏るとタイムアウトするため、ページ単位で全シャードに分散して負荷を均等化する。
# 新たに大きいカテゴリを見つけたらここに追加する（現行データの items/10 ではなく実ページ数で判断）。
BIG_CATEGORIES = {
    "0602001", "0611001", "0208003", "0605002", "0208005", "0606001",
    "0401006", "1501001", "0801001", "0801", "0610005", "0605003",
    "0206007", "0506010", "1401001", "0607003", "0801008", "0206018",
    "0610001", "0104002", "1401004", "0208012", "1401003", "0208004",
    "0104003", "0611002", "0605006", "0209001", "0203008", "0208015",
    "0207002", "0205", "0801010", "0610004", "0601003", "0206012",
    "0801005", "0607004", "0603001", "0506012", "0303001", "0610006",
    "0609001", "0605005", "0208001", "0206011", "1401002", "0206001",
    "1501002", "0801026", "0801019", "0605007", "0602009", "0505005",
    "0401002", "0204002", "1501004", "1001001", "0609002", "0304007",
    "0303002", "0204001",
}

parser = argparse.ArgumentParser()
parser.add_argument("--shard",        type=int, default=0, help="このジョブのシャード番号（0始まり）")
parser.add_argument("--total-shards", type=int, default=1, help="シャード総数")
args = parser.parse_args()

scraper = MorimoriScraper()

# sitemap から全カテゴリを発見し、除外カテゴリ（cat99・冗長集約05）を外す
all_cats   = [c for c in scraper._discover_categories() if c not in EXCLUDE_FROM_LEAF]
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

# 走査タスクを構築（各タスク = 1カテゴリの走査、または大カテゴリのページ分散走査）
def scan_normal(cat_id):
    scraper._scan_category(cat_id, results, lock)

def scan_big(cat_id):
    scraper._scan_category_pages(
        cat_id, results, lock,
        page_start=args.shard + 1, page_step=args.total_shards,
    )

tasks = []
# 1) 通常カテゴリ（担当分のみ・連続走査）
tasks += [(scan_normal, c) for c in my_normal]
# 2) SITEMAP_MISSING（全シャードで走査・取りこぼし防止）
tasks += [(scan_normal, c) for c in SITEMAP_MISSING]
# 3) 大カテゴリ（ページ単位で全シャードに分散）
tasks += [(scan_big, c) for c in sorted(big_set)]

# シャード内を LEAF_WORKERS 並列で走査する（グローバルレート制限が律速）
try:
    with ThreadPoolExecutor(max_workers=LEAF_WORKERS) as executor:
        futures = {executor.submit(fn, cat): cat for fn, cat in tasks}
        for future in as_completed(futures):
            try:
                future.result()
            except MorimoriBlockedError:
                # 403/429 ブロック時は全体を止めてシャードを失敗扱いにする
                scraper._abort_event.set()
                executor.shutdown(wait=False, cancel_futures=True)
                raise
            except Exception as exc:
                # 個別カテゴリのエラーはログのみ（他カテゴリは継続）
                print(f"  [morimori] {futures[future]} error: {exc}", flush=True)
except Exception as exc:
    # ブロック等の致命的エラー時は非ゼロ終了。
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
