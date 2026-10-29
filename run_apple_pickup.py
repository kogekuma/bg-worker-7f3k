"""Apple Store 受け取り在庫の監視ループ。

  python run_apple_pickup.py --minutes 60      # 60分間、約1分ごとに確認してログを出す

いまは疎通確認の段階で、結果は標準出力に要約を出すだけ（本番への受け渡しは後で足す）。
ブロック応答（541 等）を受けたら ::error:: を出して終了コード 2 で止まる。
"""

import argparse
import random
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

import requests

from scrapers.apple_pickup.config import INTERVAL, JITTER, PARTS
from scrapers.apple_pickup.fetcher import AppleBlockedError, check_once

JST = timezone(timedelta(hours=9))

parser = argparse.ArgumentParser()
parser.add_argument("--minutes", type=float, default=60, help="ループを続ける分数")
args = parser.parse_args()

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
        print(f"::error::[apple] {now} ブロック応答 {e}（{rounds}回目・成功 {ok} 回）→ 停止", flush=True)
        sys.exit(2)
    except Exception as e:
        failed += 1
        print(f"::warning::[apple] {now} 取得失敗 {e}", flush=True)
    else:
        ok += 1
        total_bytes += res["bytes"]
        states = Counter(p["state"] for st in res["stores"].values() for p in st["parts"].values())
        n_parts = sum(len(st["parts"]) for st in res["stores"].values())
        print(f"[apple] {now} #{rounds} 店舗 {len(res['stores'])} / 型番×店舗 {n_parts}"
              f"（想定 {11 * len(PARTS)}）/ 今日 {states['today']} 明日以降 {states['later']} なし {states['none']}"
              f" / {res['requests']}回 {res['bytes'] // 1024}KB / {time.monotonic() - started:.1f}s", flush=True)
    # 次の確認まで INTERVAL ±JITTER（確認にかかった時間は差し引く）
    wait = INTERVAL * (1 + random.uniform(-JITTER, JITTER)) - (time.monotonic() - started)
    if time.monotonic() + wait >= deadline:
        break
    time.sleep(max(1, wait))

print(f"[apple] 終了: {rounds} 回中 成功 {ok} / 失敗 {failed} / 受信 {total_bytes // 1024 // 1024}MB", flush=True)
