"""10シャードファイルを結合して morimori.json を生成するスクリプト。

増分マージ方式:
  --base <path> で既存 morimori.json を読み込み、ベースデータとして使用する。
  今回スクレイプできたシャードのデータで既存データを上書き更新し、
  キャンセルされたシャードが担当していた商品は既存データを維持する。

  これにより、スケジュール実行の競合でシャードがキャンセルされても
  直前の実行で取得済みのデータが失われない。
"""

import argparse
import json
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

parser = argparse.ArgumentParser()
parser.add_argument("--base", help="既存 morimori.json のパス（フォールバックデータ）")
args = parser.parse_args()

# Step 1: 既存データをベースとして読み込む（キャンセルシャードのフォールバック用）
merged = {}
if args.base:
    try:
        with open(args.base, encoding="utf-8") as f:
            base_data = json.load(f)
        merged = dict(base_data.get("items", {}))
        print(f"[merge] ベース読み込み: {len(merged)} JANs", flush=True)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[merge] ベースファイル読み込み失敗（スキップ）: {e}", flush=True)

# Step 2: 今回スクレイプ成功したシャードのデータを収集
shard_merged = {}
updated = ""

for shard in range(10):
    filename = f"morimori_shard_{shard}.json"
    try:
        with open(filename, encoding="utf-8") as f:
            data = json.load(f)
        for jan, item in data.get("items", {}).items():
            # 同一JAN が複数シャードに存在する場合は最高値を採用（同一ラン内の重複解消）
            if jan not in shard_merged or item["price"] > shard_merged[jan]["price"]:
                shard_merged[jan] = item
        updated = data.get("updated", "")
        print(f"[merge] shard {shard}: {data['count']} JANs", flush=True)
    except FileNotFoundError:
        print(f"[merge] shard {shard}: ファイルなし（スキップ）", flush=True)

# Step 3: 今回スクレイプ結果でベースを上書き（新データ優先）
# キャンセルシャードの商品は merged（ベース）のまま維持される
merged.update(shard_merged)
print(f"[merge] ベース: {len(merged) - len(shard_merged)} JANs 維持, "
      f"新規/更新: {len(shard_merged)} JANs", flush=True)

output = {
    "updated": updated or datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"),
    "count":   len(merged),
    "items":   merged,
}

with open("morimori.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

print(f"[merge] 完了: {len(merged)} JANs → morimori.json", flush=True)
