"""買取商店 設定"""

SITE_ID   = "kaitorishouten"
SITE_NAME = "買取商店"
BASE_URL  = "https://www.kaitorishouten-co.jp"

# (ベースページパス, AJAX リスト URL)
# ベースページへのアクセスでセッション Cookie を取得してから AJAX を叩く。
# keitai と kaden のみ。nitiyouhin は専用 AJAX エンドポイントがなく Phase 6 で取得。
AJAX_CATEGORIES = [
    ("/keitai", "/products/list_keitai_new/9"),
    ("/kaden",  "/products/list_kaden_new/10"),
]

# AJAX エンドポイント間のウェイト（通常ブラウジングより長め）
# サーバーが XHR アクセスのパターンを検出しやすいため余裕を持たせる
AJAX_DELAY     = 3.0  # 秒

# 通常カテゴリページ間のウェイト（ブラウジング相当）
CATEGORY_DELAY = 2.5  # 秒（連続 403 対策で 1.5→2.5 に変更）

# Phase 3/4 の ThreadPoolExecutor ワーカー数
MAX_WORKERS    = 5

# Phase 5（kaden list_category）のワーカー数
# 並列数が多いと 403 が頻発するため抑制
PHASE5_WORKERS = 1

# Phase 6（nitiyouhin list_category）のワーカー数
# ウィスキー・日本酒・ワイン等 21カテゴリ。Phase 5 と同じ理由で低並列に抑制
PHASE6_WORKERS = 1
