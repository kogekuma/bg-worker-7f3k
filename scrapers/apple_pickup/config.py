"""Apple Store 受け取り在庫の監視 設定

取得元: https://www.apple.com/jp/shop/retail/pickup-message
  ?pl=true&location=<郵便番号>&parts.0=<型番>&parts.1=...
  location の近くの店舗（最大6店ほど）について、型番ごとの受け取り可否が返る。
  1回に返る型番は最大20（21個目以降は無視される）ので、型番は20個ずつに分けて問い合わせる。

参考: bilune/apple-pickup-monitor（MIT）。間隔は同じ 60秒±15%。
同リポジトリによると Apple はデータセンター IP に HTTP 541 を返す（Fly.io は数時間でブロック）。
541/403/429 を受けたらその回で止め、プロキシ等での回避はしない（ユーザー方針）。
Apple から削除要請が来たら機能ごと止めて削除する（ユーザー方針・2026-10-29）。
"""

ENDPOINT = "https://www.apple.com/jp/shop/retail/pickup-message"

# 1回の問い合わせに入れる型番の上限（実測: 40個入れても20個しか返らない）
PARTS_PER_REQUEST = 20

# 問い合わせ地点（郵便番号）→ 返ってくる店舗（2026-10-29 実測）。3地点で国内11店舗すべて。
LOCATIONS = {
    "104-0061": "東京（銀座・丸の内・表参道・渋谷・新宿・川崎）",
    "530-0017": "大阪（梅田・心斎橋・京都・名古屋栄）",
    "810-0001": "福岡",
}

# 監視する型番 → 商品名（Apple の購入ページの JSON から。2026-10-29 時点）
# iPhone 18 Pro / 18 Pro Max / Duo（ユーザー指定）。新色・新容量が出たら足す。
PARTS = {
    # iPhone 18 Pro
    "MJR54J/A": "iPhone 18 Pro 256GB Black",
    "MJR64J/A": "iPhone 18 Pro 256GB Silver",
    "MJR74J/A": "iPhone 18 Pro 256GB Burgundy",
    "MJR84J/A": "iPhone 18 Pro 256GB Glacier",
    "MJR94J/A": "iPhone 18 Pro 512GB Black",
    "MJRC4J/A": "iPhone 18 Pro 512GB Silver",
    "MJRD4J/A": "iPhone 18 Pro 512GB Burgundy",
    "MJRE4J/A": "iPhone 18 Pro 512GB Glacier",
    "MJRF4J/A": "iPhone 18 Pro 1TB Black",
    "MJRG4J/A": "iPhone 18 Pro 1TB Silver",
    "MJRH4J/A": "iPhone 18 Pro 1TB Burgundy",
    "MJRJ4J/A": "iPhone 18 Pro 1TB Glacier",
    "MJRK4J/A": "iPhone 18 Pro 2TB Black",
    "MJRL4J/A": "iPhone 18 Pro 2TB Silver",
    "MJRM4J/A": "iPhone 18 Pro 2TB Burgundy",
    "MJRN4J/A": "iPhone 18 Pro 2TB Glacier",
    # iPhone 18 Pro Max
    "MJX54J/A": "iPhone 18 Pro Max 256GB Black",
    "MJX64J/A": "iPhone 18 Pro Max 256GB Silver",
    "MJX74J/A": "iPhone 18 Pro Max 256GB Burgundy",
    "MJX84J/A": "iPhone 18 Pro Max 256GB Glacier",
    "MJX94J/A": "iPhone 18 Pro Max 512GB Black",
    "MJXA4J/A": "iPhone 18 Pro Max 512GB Silver",
    "MJXC4J/A": "iPhone 18 Pro Max 512GB Burgundy",
    "MJXD4J/A": "iPhone 18 Pro Max 512GB Glacier",
    "MJXE4J/A": "iPhone 18 Pro Max 1TB Black",
    "MJXF4J/A": "iPhone 18 Pro Max 1TB Silver",
    "MJXG4J/A": "iPhone 18 Pro Max 1TB Burgundy",
    "MJXH4J/A": "iPhone 18 Pro Max 1TB Glacier",
    "MJXJ4J/A": "iPhone 18 Pro Max 2TB Black",
    "MJXK4J/A": "iPhone 18 Pro Max 2TB Silver",
    "MJXL4J/A": "iPhone 18 Pro Max 2TB Burgundy",
    "MJXM4J/A": "iPhone 18 Pro Max 2TB Glacier",
    # iPhone Duo
    "MK244J/A": "iPhone Duo 256GB Star White",
    "MK254J/A": "iPhone Duo 256GB Night Sky",
    "MK264J/A": "iPhone Duo 512GB Star White",
    "MK274J/A": "iPhone Duo 512GB Night Sky",
    "MK284J/A": "iPhone Duo 1TB Star White",
    "MK294J/A": "iPhone Duo 1TB Night Sky",
    "MK2A4J/A": "iPhone Duo 2TB Star White",
    "MK2C4J/A": "iPhone Duo 2TB Night Sky",
}

# 間隔（秒）。毎回 ±JITTER の割合でゆらがせる（参考実装と同じ）
INTERVAL = 60
JITTER = 0.15
# 1回の確認の中で、問い合わせとの間に空ける秒数（6回を一気に送らない）
REQUEST_GAP = 2.0
