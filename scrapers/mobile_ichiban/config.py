"""モバイル一番 設定"""

SITE_ID   = "mobile_ichiban"
SITE_NAME = "モバイル一番"
BASE_URL  = "https://www.mobile-ichiban.com"

REQUEST_DELAY_MIN = 1.5
REQUEST_DELAY_MAX = 2.5

MAX_WORKERS = 4

# 取得対象の大カテゴリ ID（ホームページの a.ul-max-a の id 属性と一致）
CAT_IDS = ["1", "2", "3", "4"]
