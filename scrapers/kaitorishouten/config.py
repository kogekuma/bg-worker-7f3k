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

# AJAX エンドポイント間のウェイト（Phase 1 の直列ハンドシェイク用）
AJAX_DELAY     = 3.0  # 秒

# サイト全体で共有するグローバルレート制限（秒）。
# 各 worker の sleep ではなく「kaitorishouten 宛ての次リクエストまで空ける最小間隔」。
# これで各フェーズの並列数を上げても単一runのIPからの総リクエスト速度を約1req/秒に抑える。
# 現在は GitHub Actions（run毎に新規IP）で実行のため、VPS固定IP時代の保守値より緩めてよい。
# 24h 403ゼロなら 0.8〜1.2 へ短縮可。403が出たら 1.2〜1.8 に戻す（段階運用）。
GLOBAL_MIN_INTERVAL_MIN = 0.9
GLOBAL_MIN_INTERVAL_MAX = 1.3

# Phase 3/4（category/3・category/4）の ThreadPoolExecutor ワーカー数
MAX_WORKERS    = 4

# Phase 5（kaden list_category）のワーカー数。旧 VPS単一IPでは 1（403対策）だったが、
# GitHub 新規IP＋グローバルレート制限があるため 3 に引き上げ（30分→数分の主眼）
PHASE5_WORKERS = 3

# Phase 6（nitiyouhin list_category）のワーカー数（酒類等21カテゴリ）
PHASE6_WORKERS = 2
