"""シャードファイルを結合して morimori.json を生成するスクリプト（scope 対応）。

leaf 走査（run_morimori.py）と cat99 走査（run_morimori_cat99.py）は別ワークフロー
として動くため、merge も scope ごとに呼び出す:

  --scope leaf  --shards 20  → morimori_shard_{0..19}.json を取り込む
  --scope cat99 --shards 10  → morimori_cat99_shard_{0..9}.json を取り込む

増分マージ方式:
  --base <path> で既存 morimori.json（leaf+cat99 両方を含む最新版）を読み込み、
  今回 scope のシャードデータだけで上書き更新する。もう一方の scope の商品や、
  キャンセルされたシャードが担当していた商品はベースのまま維持される。
  今回スクレイプできた JAN は現在価格なので、値下げでも fresh を無条件採用する
  （最高値保持だと値下げが永久に反映されず古い高値が固着するため）。
  leaf と cat99 の JAN は実測上ほぼ重複しないが、衝突時は今回 scope（fresh）を優先する。

古いデータの掃除（2026-10-30〜）:
  増分マージは消さないので、サイトから消えた・価格非表示（現在価格 ASK）になった商品の価格が
  いつまでも残っていた（10-08 のデザイン刷新後、「[予約必須]」約7,000件が旧価格のまま＝全体の約4割）。
  各商品に最後に取れた時刻 seen（UNIX 秒）を持たせ、STALE_DROP_HOURS 取れていない商品は落とす。
  seen の無い旧データは今回の時刻を入れて猶予を与える（初回でいきなり消さない）。
  leaf・cat99 とも30分ごとに全カテゴリを回るので、48時間はシャードの失敗が続いても消えない余裕がある。
"""

import argparse
import json
import time
from datetime import datetime, timezone, timedelta

JST = timezone(timedelta(hours=9))
STALE_DROP_HOURS = 48

parser = argparse.ArgumentParser()
parser.add_argument("--base", help="既存 morimori.json のパス（フォールバックデータ）")
parser.add_argument("--scope", choices=["leaf", "cat99"], default="leaf",
                    help="取り込むシャードの種別")
parser.add_argument("--shards", type=int, default=10, help="シャード総数")
parser.add_argument(
    "--expect", default=None,
    help="このワークフローが生成するはずのシャード範囲 'start-end'（例 20-39）。"
         "leaf は A(0-19)/B(20-39) で半分ずつ動くので、指定が無いと"
         "もう一方の20本を『欠損』と誤検知する。省略時は全シャードを期待値とする。",
)
args = parser.parse_args()

if args.expect:
    _s, _, _e = args.expect.partition("-")
    expected_shards = set(range(int(_s), int(_e or _s) + 1))
else:
    expected_shards = set(range(args.shards))

prefix = "morimori_shard_" if args.scope == "leaf" else "morimori_cat99_shard_"

# Step 1: 既存データをベースとして読み込む（もう一方の scope・キャンセル分の維持用）
merged = {}
if args.base:
    try:
        with open(args.base, encoding="utf-8") as f:
            base_data = json.load(f)
        merged = dict(base_data.get("items", {}))
        print(f"[merge:{args.scope}] ベース読み込み: {len(merged)} JANs", flush=True)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[merge:{args.scope}] ベースファイル読み込み失敗（スキップ）: {e}", flush=True)

# Step 2: 今回 scope のシャードデータを収集（同一ラン内の重複は最高値）
shard_merged = {}
updated = ""
ok_shards = 0
missing_shards = []   # ファイルなし＝そのシャードは丸ごと空振り（担当カテゴリが更新されない）
partial_shards = []   # 走査予算オーバーで途中打ち切り

for shard in range(args.shards):
    filename = f"{prefix}{shard}.json"
    try:
        with open(filename, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"[merge:{args.scope}] shard {shard}: ファイルなし（スキップ）", flush=True)
        # 期待範囲内の欠損だけを「取りこぼし」として扱う
        # （leaf-A から見た 20-39 のように、もう一方のワークフロー担当分は正常な不在）
        if shard in expected_shards:
            missing_shards.append(shard)
        continue

    for jan, item in data.get("items", {}).items():
        if jan not in shard_merged or item["price"] > shard_merged[jan]["price"]:
            shard_merged[jan] = item
    updated = data.get("updated", "") or updated
    ok_shards += 1
    if data.get("partial"):
        partial_shards.append(shard)
    print(
        f"[merge:{args.scope}] shard {shard}: {data.get('count', 0)} JANs"
        f"{'（部分）' if data.get('partial') else ''}",
        flush=True,
    )

# 欠けたシャードは「そのカテゴリだけ静かに古くなる」ので run サマリに出す。
# （merge は if: always() なので他シャードは反映され、run の赤/緑では判別できない）
if missing_shards:
    print(f"::warning::[merge:{args.scope}] データ無しシャード {len(missing_shards)} 本: "
          f"{missing_shards} — 担当カテゴリは前回値のまま", flush=True)
if partial_shards:
    print(f"::warning::[merge:{args.scope}] 予算超過で部分取得のシャード {len(partial_shards)} 本: "
          f"{partial_shards}", flush=True)

# 全シャードが 0 件＝サイトの HTML 変更などで何も読めていない。
# ここで書き出すと updated だけ進んで前回データが「最新」に見え、鮮度監視も気づかない
# （2026-10-08〜16 に実際に起きた: 一覧のデザイン刷新で全件 0 件のまま約8日間価格が止まった）。
# 書き出さずに失敗終了し、run を赤にする（updated が進まないので VPS の鮮度監視も通知する）。
if not shard_merged:
    print(f"::error::[merge:{args.scope}] 全シャードで 0 件。サイト側の変更を疑ってください"
          f"（morimori.json は更新しません）", flush=True)
    raise SystemExit(1)

# Step 3: 今回 scope の結果でベースを上書き。
# 今回スクレイプできた JAN は「現在の買取価格」なので、値下げでも fresh を無条件採用する。
# （最高値保持にすると価格が下がったときに永久に古い高値が残り続けるバグになる。
#   未スクレイプの JAN＝もう一方の scope やキャンセルされたシャードの分は base のまま維持される。）
now_ts = int(time.time())
for item in shard_merged.values():
    item["seen"] = now_ts
merged.update(shard_merged)

# 長く取れていない商品を落とす（seen の無い旧データは今回の時刻で猶予を与える）
dropped = 0
for jan in list(merged):
    seen = merged[jan].setdefault("seen", now_ts)
    if now_ts - seen > STALE_DROP_HOURS * 3600:
        del merged[jan]
        dropped += 1
if dropped:
    print(f"[merge:{args.scope}] {STALE_DROP_HOURS}時間取れていない {dropped} JANs を削除", flush=True)

print(f"[merge:{args.scope}] {ok_shards}/{args.shards} シャード取り込み, "
      f"新規/更新 {len(shard_merged)} JANs, 合計 {len(merged)} JANs", flush=True)

output = {
    "updated": updated or datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"),
    "count":   len(merged),
    "items":   merged,
}

with open("morimori.json", "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

print(f"[merge:{args.scope}] 完了: {len(merged)} JANs → morimori.json", flush=True)
