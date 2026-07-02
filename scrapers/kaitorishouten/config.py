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
# 全 worker で共有するため、これが総リクエスト速度の上限になる（並列数ではなくこの値が律速）。
# 0.3〜0.5秒 ≒ 約2.5req/秒。旧 Phase 3/4 が5並列で実質2req/秒で GitHub上403なく動いていた
# 実績＋α。全 worker 共有なのでこれが総速度の律速。worker はサーバの遅延を隠す用途。
# GitHub新規IP前提。403が出たら 0.7〜1.0 に戻す（段階運用）。
GLOBAL_MIN_INTERVAL_MIN = 0.3
GLOBAL_MIN_INTERVAL_MAX = 0.5

# Phase 3/4（category/3・category/4）の ThreadPoolExecutor ワーカー数。
# kaitorishouten はサーバ応答が負荷時に遅くなる（深いページで read timeout も発生）ため、
# worker を多めにしてレイテンシを隠す（レート上限はグローバル制限が担う）
MAX_WORKERS    = 6

# Phase 5（kaden list_category）のワーカー数。旧 VPS単一IPでは 1（403対策）だったが、
# GitHub 新規IP＋グローバルレート制限があるため 5 に引き上げ（30分→数分の主眼）
PHASE5_WORKERS = 5

# Phase 6（nitiyouhin list_category）のワーカー数（酒類等21カテゴリ）
PHASE6_WORKERS = 2
