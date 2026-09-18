"""買取商店 設定"""

SITE_ID   = "kaitorishouten"
SITE_NAME = "買取商店"
BASE_URL  = "https://www.kaitorishouten-co.jp"

# 2026-09-04 のサイト刷新（React SPA 化）後の公開 JSON API。
# フロント（/assets/real-*.js）が叩いている /api/v1 をそのまま使う。
#   GET /api/v1/products?per_page=100&perPage=100&page=N
#     → {"items":[...], "page":N, "per_page":100, "total":7710}
#   per_page は 100 が上限（それ以上を指定しても 100 に丸められる）。
#   フロントは per_page と perPage の両方を付けるので同じにしておく。
API_PRODUCTS_URL = BASE_URL + "/api/v1/products"
API_PER_PAGE     = 100

# 商品個別ページ（結果 JSON の url に使う。SPA なので実体は同じ index.html）
PRODUCT_URL = BASE_URL + "/products/detail/{}"

# ページ間ウェイト（秒）。1ページ約0.4秒応答・78ページなので 0.6〜1.2 秒で 1〜2 分に収まる
PAGE_DELAY_MIN = 0.6
PAGE_DELAY_MAX = 1.2

# 途中で総件数が減るなど整合性が崩れたときの取得打ち切り上限（無限ループ防止）
MAX_PAGES = 400
