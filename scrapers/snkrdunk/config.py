"""スニダン 設定"""

SITE_ID   = "snkrdunk"
SITE_NAME = "スニダン"
BASE_URL  = "https://snkrdunk.com"
API_URL   = "https://snkrdunk.com/en/v1/search"

# シングルカード等の低価格品をBOX参考価格として取り込まないための最低価格フィルター
MIN_PRICE = 500

# BOX商品判定キーワード（box_only=True の場合に使用）
BOX_KEYWORDS    = ["box", "ボックス"]
# カートン商品判定キーワード（carton_only=True の場合に使用）
CARTON_KEYWORDS = ["carton", "カートン"]

# 取得対象キーワードと絞り込みの設定
# box_only=True   : 商品名に「box」または「ボックス」を含むもののみ
# carton_only=True: 商品名に「carton」または「カートン」を含むもののみ
# 「ポケモンカードゲームMEGA」は英語商品名を持つMEGA世代拡張パックのマッチングに必要
SEARCH_TARGETS = [
    {"keyword": "ポケモンカード",           "box_only": False},
    {"keyword": "ポケモンカードゲームMEGA",  "box_only": False},
    {"keyword": "ワンピースカード",          "box_only": True},
    {"keyword": "ワンピースカード",          "carton_only": True},
]