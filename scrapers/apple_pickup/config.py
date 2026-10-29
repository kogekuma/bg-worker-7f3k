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

# 監視する型番 → (JAN, 商品名)。型番は Apple の購入ページの JSON（partNumber と英語名）から、
# JAN は Scanner の name_overrides.json の同じ商品名から引いた（2026-10-29・40件すべて一致）。
# iPhone 18 Pro / 18 Pro Max / Duo（ユーザー指定）。新色・新容量が出たら足す。
PARTS = {
    # iPhone 18 Pro
    "MJR54J/A": ("4549995734140", "iPhone 18 Pro 256GB ブラック"),
    "MJR64J/A": ("4549995734157", "iPhone 18 Pro 256GB シルバー"),
    "MJR74J/A": ("4549995734164", "iPhone 18 Pro 256GB バーガンディ"),
    "MJR84J/A": ("4549995734171", "iPhone 18 Pro 256GB グレイシャー"),
    "MJR94J/A": ("4549995734188", "iPhone 18 Pro 512GB ブラック"),
    "MJRC4J/A": ("4549995734195", "iPhone 18 Pro 512GB シルバー"),
    "MJRD4J/A": ("4549995734201", "iPhone 18 Pro 512GB バーガンディ"),
    "MJRE4J/A": ("4549995734218", "iPhone 18 Pro 512GB グレイシャー"),
    "MJRF4J/A": ("4549995734225", "iPhone 18 Pro 1TB ブラック"),
    "MJRG4J/A": ("4549995734232", "iPhone 18 Pro 1TB シルバー"),
    "MJRH4J/A": ("4549995734249", "iPhone 18 Pro 1TB バーガンディ"),
    "MJRJ4J/A": ("4549995734256", "iPhone 18 Pro 1TB グレイシャー"),
    "MJRK4J/A": ("4549995734263", "iPhone 18 Pro 2TB ブラック"),
    "MJRL4J/A": ("4549995734270", "iPhone 18 Pro 2TB シルバー"),
    "MJRM4J/A": ("4549995734287", "iPhone 18 Pro 2TB バーガンディ"),
    "MJRN4J/A": ("4549995734294", "iPhone 18 Pro 2TB グレイシャー"),
    # iPhone 18 Pro Max
    "MJX54J/A": ("4549995734546", "iPhone 18 Pro Max 256GB ブラック"),
    "MJX64J/A": ("4549995734591", "iPhone 18 Pro Max 256GB シルバー"),
    "MJX74J/A": ("4549995734645", "iPhone 18 Pro Max 256GB バーガンディ"),
    "MJX84J/A": ("4549995734690", "iPhone 18 Pro Max 256GB グレイシャー"),
    "MJX94J/A": ("4549995734744", "iPhone 18 Pro Max 512GB ブラック"),
    "MJXA4J/A": ("4549995734799", "iPhone 18 Pro Max 512GB シルバー"),
    "MJXC4J/A": ("4549995734843", "iPhone 18 Pro Max 512GB バーガンディ"),
    "MJXD4J/A": ("4549995734898", "iPhone 18 Pro Max 512GB グレイシャー"),
    "MJXE4J/A": ("4549995734942", "iPhone 18 Pro Max 1TB ブラック"),
    "MJXF4J/A": ("4549995734997", "iPhone 18 Pro Max 1TB シルバー"),
    "MJXG4J/A": ("4549995735048", "iPhone 18 Pro Max 1TB バーガンディ"),
    "MJXH4J/A": ("4549995735093", "iPhone 18 Pro Max 1TB グレイシャー"),
    "MJXJ4J/A": ("4549995735147", "iPhone 18 Pro Max 2TB ブラック"),
    "MJXK4J/A": ("4549995735192", "iPhone 18 Pro Max 2TB シルバー"),
    "MJXL4J/A": ("4549995735246", "iPhone 18 Pro Max 2TB バーガンディ"),
    "MJXM4J/A": ("4549995735291", "iPhone 18 Pro Max 2TB グレイシャー"),
    # iPhone Duo
    "MK244J/A": ("4549995732641", "iPhone Duo 256GB スターホワイト"),
    "MK254J/A": ("4549995732696", "iPhone Duo 256GB ナイトスカイ"),
    "MK264J/A": ("4549995732740", "iPhone Duo 512GB スターホワイト"),
    "MK274J/A": ("4549995732795", "iPhone Duo 512GB ナイトスカイ"),
    "MK284J/A": ("4549995732849", "iPhone Duo 1TB スターホワイト"),
    "MK294J/A": ("4549995732894", "iPhone Duo 1TB ナイトスカイ"),
    "MK2A4J/A": ("4549995732948", "iPhone Duo 2TB スターホワイト"),
    "MK2C4J/A": ("4549995732993", "iPhone Duo 2TB ナイトスカイ"),
}

# 間隔（秒）。毎回 ±JITTER の割合でゆらがせる（参考実装と同じ）
INTERVAL = 60
JITTER = 0.15
# 1回の確認の中で、問い合わせとの間に空ける秒数（6回を一気に送らない）
REQUEST_GAP = 2.0
