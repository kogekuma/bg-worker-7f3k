"""スニダン 設定"""

SITE_ID   = "snkrdunk"
SITE_NAME = "スニダン"
BASE_URL  = "https://snkrdunk.com"
API_URL   = "https://snkrdunk.com/en/v1/search"

# シングルカード等の低価格品をBOX参考価格として取り込まないための最低価格フィルター
# ポケモンカードBOXは最低でも数百円以上するため、それ以下は除外する
MIN_PRICE = 500

# 取得対象キーワードと BOX 絞り込みの設定
# box_only=True の場合、商品名に「box」または「ボックス」を含むもののみ取得
# 「ポケモンカードゲームMEGA」は英語商品名を持つMEGA世代拡張パック（アビスアイ等）のマッチングに必要
SEARCH_TARGETS = [
    {"keyword": "ポケモンカード",          "box_only": False},
    {"keyword": "ポケモンカードゲームMEGA", "box_only": False},
    {"keyword": "ワンピースカード",         "box_only": True},
]