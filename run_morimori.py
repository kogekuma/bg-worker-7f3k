"""森森買取 leaf カテゴリ走査（シャード対応・cat99 除外）。

--shard N --total-shards M で leaf カテゴリを M 分割して担当分のみ取得する。
全商品集約カテゴリ cat99 は別ワークフロー run_morimori_cat99.py が担当するため
ここでは除外する。

シャード設計（Phase0 計測: 商品ありページの応答中央値 ~7.5秒）:
  - 通常カテゴリ: カテゴリ単位で stride 分割（cats[shard::total]）。多くは1ページ。
  - 大カテゴリ（BIG_CATEGORIES, 12ページ超）: 1シャードに偏ると14分窓を超えるため、
    ページ単位で全シャードに分散（shard k は page k+1, k+1+total, ...）。
  - SITEMAP_MISSING: discovery が必ず含めるため通常/大カテゴリ側で自然にカバーされる。

  leaf 全体は約2708ページ（商品はほぼ全て新品・複数カテゴリに重複掲載）ある。
  サーバは高並列に耐えられない（20シャード×並列で過負荷になり全滅する実測あり）ため、
  シャード内は直列（1接続）に保つ。総ページを減らすには重複掲載の集約カテゴリ除外や
  シャード数の調整で対応する。

結果を morimori_shard_{N}.json として出力する（merge_morimori.py が増分マージ）。
"""

import argparse
import json
import threading
from datetime import datetime, timezone, timedelta

from scrapers.morimori import MorimoriScraper
from scrapers.morimori.scraper import AGGREGATE_CATEGORY

JST = timezone(timedelta(hours=9))

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

# sitemap から全カテゴリを発見し、除外カテゴリ（cat99・冗長集約05）を外す。
# _discover_categories は SITEMAP_MISSING を必ず union するため、SITEMAP カテゴリも
# all_cats に含まれる。よって小さい SITEMAP カテゴリは通常 stride で、大きいもの
# （0104002/0104003 等）は BIG のページ分散で自然にカバーされる。
# （旧実装は SITEMAP を全シャードで別途フル走査しており、大 SITEMAP カテゴリを
#   各シャードで全走査＋BIGで二重走査してタイムアウトの主因になっていた）
all_cats   = [c for c in scraper._discover_categories() if c not in EXCLUDE_FROM_LEAF]
big_set    = {c for c in BIG_CATEGORIES if c in all_cats}

# 通常カテゴリ（大カテゴリ以外・小 SITEMAP を含む）を stride 分割
normal_cats = [c for c in all_cats if c not in big_set]
my_normal   = normal_cats[args.shard::args.total_shards]

print(
    f"[morimori leaf shard {args.shard}/{args.total_shards}] "
    f"通常 {len(my_normal)} / 大 {len(big_set)}(ページ分散) / 全カテゴリ {len(all_cats)}",
    flush=True,
)

results: dict = {}
lock = threading.Lock()

# 直列走査（サーバは高並列に耐えられないため、シャード内は1接続に保つ。
# 並列化すると 20シャード×並列数の同時接続でサーバが過負荷になり全滅する）。
try:
    # 1) 通常カテゴリ（担当分のみ・連続走査。小 SITEMAP カテゴリもここに含まれる）
    for cat_id in my_normal:
        scraper._scan_category(cat_id, results, lock)

    # 2) 大カテゴリ（ページ単位で全シャードに分散。大 SITEMAP もここで処理される）
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
