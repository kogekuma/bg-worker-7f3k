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


# モジュールロード時に mobile_mix の JAN_MAP から iPhone グループを構築する。
IPHONE_JAN_GROUPS = build_model_capacity_jan_groups(MOBILE_MIX_JAN_MAP)
