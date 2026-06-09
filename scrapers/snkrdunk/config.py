"""スニダン 設定"""

SITE_ID   = "snkrdunk"
SITE_NAME = "スニダン"
BASE_URL  = "https://snkrdunk.com"
API_URL   = "https://snkrdunk.com/en/v1/search"

# シングルカードの低価格品を除外するための最低価格フィルター
MIN_PRICE = 500

# 取得対象キーワードと BOX 絞り込みの設定
# box_only=True の場合、商品名に「box」または「ボックス」を含むもののみ取得
# max_pages: 指定した場合そのページ数で打ち切り（429 レートリミット対策）
SEARCH_TARGETS = [
    {"keyword": "ポケモンカード",           "box_only": False, "max_pages": 25},
    {"keyword": "ポケモンカードゲームMEGA", "box_only": False, "max_pages": 10},
]
