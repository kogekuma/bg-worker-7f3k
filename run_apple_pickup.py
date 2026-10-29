"""Apple Store 受け取り在庫の監視ループ。

  python run_apple_pickup.py --minutes 340     # 340分間、約1分ごとに確認する
  python run_apple_pickup.py --once            # 1回だけ確認して終わる（ジョブごとに IP が変わる起動方式用）

環境変数 NEDAN_INGEST_KEY（nedan. 管理画面で発行する投稿用 API キー nk_…）があれば、
毎回の結果を nedan. の API（POST /api/ingest/apple-stock）へ送る。無ければ標準出力に要約を出すだけ。

ブロック応答（541 等）を受けたら、サイトに「停止中」を伝えてから ::error:: を出し、終了コード 2 で止まる
（回避はしない。次のスケジュール起動でまた試す）。
"""

import argparse
import os
import random
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

import requests

from scrapers.apple_pickup.config import INTERVAL, JITTER, PARTS
from scrapers.apple_pickup.fetcher import AppleBlockedError, check_once

JST = timezone(timedelta(hours=9))
INGEST_URL = os.environ.get("NEDAN_INGEST_URL", "https://nedan-check.com/api/ingest/apple-stock")
INGEST_KEY = os.environ.get("NEDAN_INGEST_KEY", "")

parser = argparse.ArgumentParser()
parser.add_argument("--minutes", type=float, default=60, help="ループを続ける分数")
parser.add_argument("--once", action="store_true", help="1回だけ確認して終わる")
args = parser.parse_args()


def send(payload: dict) -> None:
    """結果を nedan. へ送る（キーが無ければ何もしない。失敗しても監視は続ける）。"""
    if not INGEST_KEY:
        return
    try:
        r = requests.post(INGEST_URL, json=payload, timeout=20,
                          headers={"Authorization": f"Bearer {INGEST_KEY}"})
        if r.status_code != 200:
            print(f"::warning::[apple] 送信失敗 HTTP {r.status_code} {r.text[:200]}", flush=True)
    except requests.RequestException as e:
        print(f"::warning::[apple] 送信失敗 {e}", flush=True)


def to_payload(res: dict) -> dict:
    """型番を JAN に置き換え、サイトが使う形にする。

    {"checkedAt": ISO8601, "stores": {店番号: {"name": 店名, "items": {JAN: {"s": today|later|none, "q": 文言}}}}}
    """
    stores = {}
    for number, st in res["stores"].items():
        items = {}
        for part, info in st["parts"].items():
            if part in PARTS:
                items[PARTS[part][0]] = {"s": info["state"], "q": info["quote"]}
        stores[number] = {"name": st["name"], "items": items}
    return {"checkedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "stores": stores}


session = requests.Session()
deadline = time.monotonic() + args.minutes * 60
rounds = ok = failed = 0
total_bytes = 0

while time.monotonic() < deadline:
    rounds += 1
    started = time.monotonic()
    now = datetime.now(JST).strftime("%H:%M:%S")
    try:
        res = check_once(session)
    except AppleBlockedError as e:
        send({"checkedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "blocked": str(e)})
        print(f"::error::[apple] {now} ブロック応答 {e}（{rounds}回目・成功 {ok} 回）→ 停止", flush=True)
        sys.exit(2)
    except Exception as e:
        failed += 1
        print(f"::warning::[apple] {now} 取得失敗 {e}", flush=True)
    else:
        ok += 1
        total_bytes += res["bytes"]
        send(to_payload(res))
        states = Counter(p["state"] for st in res["stores"].values() for p in st["parts"].values())
        n_parts = sum(len(st["parts"]) for st in res["stores"].values())
        print(f"[apple] {now} #{rounds} 店舗 {len(res['stores'])} / 型番×店舗 {n_parts}"
              f"（想定 {11 * len(PARTS)}）/ 今日 {states['today']} 明日以降 {states['later']} なし {states['none']}"
              f" / {res['requests']}回 {res['bytes'] // 1024}KB / {time.monotonic() - started:.1f}s", flush=True)
    if args.once:
        break
    # 次の確認まで INTERVAL ±JITTER（確認にかかった時間は差し引く）
    wait = INTERVAL * (1 + random.uniform(-JITTER, JITTER)) - (time.monotonic() - started)
    if time.monotonic() + wait >= deadline:
        break
    time.sleep(max(1, wait))

print(f"[apple] 終了: {rounds} 回中 成功 {ok} / 失敗 {failed} / 受信 {total_bytes // 1024 // 1024}MB", flush=True)
