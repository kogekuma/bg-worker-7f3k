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
# 旧 1 は VPS単一IPの403対策。現在は GitHub Actions（run毎に新規IP）実行で、Phase 3/4 が
# 5並列で問題なく動いている実績があるため、同じ枠組み（per-worker 2.5秒遅延・グローバル
# 制限なし）のまま 4 に引き上げる。Phase 5 の30分がボトルネックだったため約7分に短縮見込み。
# ※ グローバルレート制限方式はこのサーバに不適合（適応的に遅くなる）と実証済みのため、
#    元の per-worker 遅延方式を維持し worker だけ増やす。
PHASE5_WORKERS = 4

# Phase 6（nitiyouhin list_category）のワーカー数（酒類等21カテゴリ）
PHASE6_WORKERS = 2
