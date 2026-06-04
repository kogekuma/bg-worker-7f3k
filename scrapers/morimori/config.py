"""森森買取 設定"""

SITE_ID   = "morimori"
SITE_NAME = "森森買取"
BASE_URL  = "https://www.morimori-kaitori.jp"

# GitHub Actions 上では IP ブロックが発生しないため元の設定に戻す
REQUEST_DELAY_MIN = 1.0
REQUEST_DELAY_MAX = 2.0

PAGE_SIZE   = 10
MAX_WORKERS = 5
