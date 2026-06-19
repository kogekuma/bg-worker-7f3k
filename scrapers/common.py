"""共通ユーティリティ（extract_jan, extract_price, merge_into_results）。"""

import re


def extract_jan(text: str) -> str | None:
    """文字列から JAN コード（8〜13桁の数字）を抽出して返す。"""
    if not text:
        return None
    # 不可視 Unicode 文字（LRM 等）を除去してから数字のみ抽出
    text = re.sub(r"[‎‏​‌‍﻿]", "", text)
    digits = re.sub(r"[^0-9]", "", text)
    if 8 <= len(digits) <= 13:
        return digits
    return None


def extract_price(text: str) -> int | None:
    """価格文字列から整数値（円）を抽出して返す。"""
    if not text:
        return None
    digits = re.sub(r"[^0-9]", "", text)
    if not digits:
        return None
    return int(digits)


def merge_into_results(results: dict, jan: str, name: str, price: int, url: str, force: bool = False):
    """results に (jan, name, price, url) をマージする。
    通常は高い価格を採用。force=True の場合は既存価格より低くても上書き（カテゴリページ優先用）。"""
    if jan not in results:
        results[jan] = {"name": name, "price": price, "url": url}
    elif force or price > results[jan]["price"]:
        results[jan] = {"name": name, "price": price, "url": url}
