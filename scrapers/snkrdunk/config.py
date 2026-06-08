"""スニダン 設定"""

SITE_ID   = "snkrdunk"
SITE_NAME = "スニダン"
BASE_URL  = "https://snkrdunk.com"
API_URL   = "https://snkrdunk.com/en/v1/search"

# 取得対象キーワードと BOX 絞り込みの設定
# box_only=True の場合、商品名に「box」または「ボックス」を含むもののみ取得
SEARCH_TARGETS = [
    {"keyword": "ポケモンカード",   "box_only": False},
    {"keyword": "ワンピースカード", "box_only": True},
]
