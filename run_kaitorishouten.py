"""買取商店スクレイパー実行スクリプト。

  --mode full|fast … 互換のため受け取るが、2026-09-18 の JSON API 化以降はどちらも
                     全件スナップショット（約 1〜2 分）。VPS cron は従来どおり
                     fast=30分ごと / full=3時間ごとに dispatch しているので両方そのまま動く。
  --base <path>    … 前回の kaitorishouten.json。縮小ガード（前回比 70% 未満なら更新しない）に使う。
                     旧構成の「fast を前回 full に上書き合成」は、全件取得になったため廃止
                     （合成すると掲載終了した商品が永久に残るので、しない方が正しい）。

結果を kaitorishouten.json として出力する。GitHub Actions から Scanner の docs/data/ に push。
失敗・0件・大幅縮小時は JSON を生成しない（＝前回データを保持）。
"""

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta

from scrapers.kaitorishouten import KaitorishoutenScraper

JST = timezone(timedelta(hours=9))

parser = argparse.ArgumentParser()
parser.add_argument("--mode", choices=["full", "fast"], default="full")
parser.add_argument("--base", help="縮小ガードの基準にする前回 kaitorishouten.json のパス")
args = parser.parse_args()

# 前回データ（縮小ガードの基準）を読み込む
base_items: dict = {}
if args.base:
    try:
        with open(args.base, encoding="utf-8") as f:
            base_items = dict(json.load(f).get("items", {}))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[kaitorishouten] base 読み込み失敗: {e}", flush=True)

try:
    data = KaitorishoutenScraper().scrape(mode=args.mode)
except Exception as e:
    print(f"[kaitorishouten] スクレイプ中断（前回データ保持）: {e}", flush=True)
    sys.exit(0)

if not data:
    print("[kaitorishouten] 0件のため更新しません（前回データ保持）", flush=True)
    sys.exit(0)

# 縮小ガード: 前回比 70% 未満なら異常とみなし更新しない（部分取得で全体を痩せさせない）
if base_items and len(data) < len(base_items) * 0.7:
    print(f"[kaitorishouten] 件数が前回の70%未満（{len(data)}/{len(base_items)}）のため更新しません", flush=True)
    sys.exit(0)

output = {
    "updated": datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"),
    "count": len(data),
    "items": data,
}

with open("kaitorishouten.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

print(f"[kaitorishouten] {args.mode} 完了: {len(data)} JANs → kaitorishouten.json", flush=True)
