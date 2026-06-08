"""5つのシャードファイルを結合して morimori.json を生成するスクリプト。

同一JANが複数シャードに存在する場合は最高値を採用する。
"""

import json
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))

merged = {}
updated = ""

for shard in range(10):
    filename = f"morimori_shard_{shard}.json"
    try:
        with open(filename, encoding="utf-8") as f:
            data = json.load(f)
        for jan, item in data.get("items", {}).items():
            # 同一JANが複数カテゴリに存在する場合は最高値を採用
            if jan not in merged or item["price"] > merged[jan]["price"]:
                merged[jan] = item
        updated = data.get("updated", "")
        print(f"[merge] shard {shard}: {data['count']} JANs", flush=True)
    except FileNotFoundError:
        print(f"[merge] shard {shard}: ファイルなし（スキップ）", flush=True)

output = {
    "updated": updated or datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"),
    "count":   len(merged),
    "items":   merged,
}

with open("morimori.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

print(f"[merge] 完了: {len(merged)} JANs → morimori.json", flush=True)
