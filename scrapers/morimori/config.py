"""森森買取 設定"""

SITE_ID   = "morimori"
SITE_NAME = "森森買取"
BASE_URL  = "https://www.morimori-kaitori.jp"

# GitHub Actions 上では IP ブロックが発生しにくいため元の設定に戻す
REQUEST_DELAY_MIN = 1.0
REQUEST_DELAY_MAX = 2.0

# サイト全体で共有するグローバルレート制限（秒）。
# 全リクエストの開始間隔をこの範囲でランダムに空けて 403/429（IPブロック）を回避する。
# morimori の商品ありページはサーバ側レンダリングが重く、実測レイテンシは
# GitHub Actions の新規 IP でも中央値 ~7.5 秒（Phase0 計測）。レイテンシが
# interval を上回るため、直列走査では追加待ちはほぼ発生しない。Codex 助言に従い
# 2-3 秒に設定（0.5-1 秒は速いがブロック誘発リスクに見合わない）。
GLOBAL_MIN_INTERVAL_MIN = 2.0
GLOBAL_MIN_INTERVAL_MAX = 3.0

# 1ページあたりの商品数上限（この件数未満 = 最終ページ判定に使用）
PAGE_SIZE   = 10

# scrape() の並列ワーカー数（run_morimori.py は直列のため未使用）
MAX_WORKERS = 2
