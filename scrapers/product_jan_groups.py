"""商品名ベースの JAN グループ生成ヘルパー。

色情報を持たない「機種+容量」名（例: mobile_ichiban の "iPhone17 Pro Max 256GB"）を、
他サイトが色別に持つ実 JAN 群へ突き合わせるための辞書を構築する。
入力は mobile_mix の色込み JAN_MAP（"iPhone17 Pro Max 256GB シルバー" → JAN）。
"""

from __future__ import annotations

import re

from scrapers.mobile_mix.jan_map import JAN_MAP as MOBILE_MIX_JAN_MAP


# 先頭から容量トークン（数字 + GB/TB）までを「機種+容量」として抽出する。
# 容量より後ろ（色名など）は含めない。
_IPHONE_MODEL_CAPACITY_RE = re.compile(r"^(.*?\b\d+(?:GB|TB))\b")


def build_model_capacity_jan_groups(jan_map: dict[str, str]) -> dict[str, set[str]]:
    """iPhone の「機種+容量」→ 全色 JAN 集合 のグループ辞書を構築する。

    jan_map のキーのうち "iPhone" で始まるものだけを対象とし、
    キーから色を除いた「機種+容量」をキーに、対応する JAN を集合へまとめる。
    """
    groups: dict[str, set[str]] = {}
    for key, jan in jan_map.items():
        if not key.startswith("iPhone"):
            continue

        match = _IPHONE_MODEL_CAPACITY_RE.search(key)
        if not match:
            continue

        model_capacity = match.group(1).strip()
        groups.setdefault(model_capacity, set()).add(jan)

    return groups


def build_jan_colors(jan_map: dict[str, str]) -> dict[str, set[str]]:
    """iPhone の JAN → 色名の集合 を構築する（2026-10-01 追加）。

    キーの容量より後ろ（"iPhone18 Pro Max 256GB グレイシャー" の "グレイシャー"）を色とみなす。
    同じ JAN に別名の色が付いていることがある（例: シルバー と ホワイト）ので集合で持つ。
    mobile_ichiban が「シルバー -32000/グレイシャー -27000」のような色別減額を
    グループ展開した JAN ごとに当てるのに使う。
    """
    colors: dict[str, set[str]] = {}
    for key, jan in jan_map.items():
        if not key.startswith("iPhone"):
            continue
        match = _IPHONE_MODEL_CAPACITY_RE.search(key)
        if not match:
            continue
        color = key[match.end():].strip()
        if color:
            colors.setdefault(jan, set()).add(color)
    return colors


# モジュールロード時に mobile_mix の JAN_MAP から iPhone グループを構築する。
IPHONE_JAN_GROUPS = build_model_capacity_jan_groups(MOBILE_MIX_JAN_MAP)
IPHONE_JAN_COLORS = build_jan_colors(MOBILE_MIX_JAN_MAP)
