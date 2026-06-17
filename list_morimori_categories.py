"""モリモリのsitemap.xmlから全カテゴリIDをリストアップするデバッグスクリプト。

sitemap.xmlに掲載されているカテゴリを全件出力し、
未掲載のVR・Steam Deck系カテゴリ候補もプローブする。
"""
import re
import time

import requests

BASE_URL = "https://morimori-kaitori.jp"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml",
}
session = requests.Session()
session.headers.update(HEADERS)

# Step 1: sitemap.xml からカテゴリを取得
print("=== sitemap.xml からカテゴリ取得 ===", flush=True)
resp = session.get(BASE_URL + "/sitemap.xml", timeout=30)
cats_in_sitemap = sorted(set(re.findall(r"/category/([^/]+)/product/\d+", resp.text)))
print(f"カテゴリ数: {len(cats_in_sitemap)}", flush=True)
for c in cats_in_sitemap:
    print(f"  {c}", flush=True)

# Step 2: sitemap未掲載の候補カテゴリをプローブ
# ゲーム機系: 0101〜0115 の 001〜003
print("\n=== 候補カテゴリのプローブ ===", flush=True)
PROBE_CATS = [
    f"01{prefix:02d}{suffix:03d}"
    for prefix in range(2, 16)
    for suffix in [1, 2, 3]
    if f"01{prefix:02d}{suffix:03d}" not in cats_in_sitemap
]
# SITEMAP_MISSING のうちまだ未掲載のもの
KNOWN_MISSING = ["0101002","0104002","0104003","0108001","0108003","0109001","0109003","0101001"]
PROBE_CATS = [c for c in PROBE_CATS if c not in KNOWN_MISSING]

# 0111・0114 の直接内容確認（status-new/old どちらも含む）
print("\n=== 0111・0114 の詳細内容確認 ===", flush=True)
for cat in ["0111", "0114"]:
    try:
        r = session.get(f"{BASE_URL}/category/{cat}", timeout=15)
        badges_new = re.findall(r'status-new', r.text)
        badges_old = re.findall(r'status-old', r.text)
        jans = re.findall(r'JAN:(\d+)', r.text)
        print(f"  {cat}: status-new={len(badges_new)}件, status-old={len(badges_old)}件, JAN={jans[:5]}", flush=True)
        time.sleep(2)
    except Exception as e:
        print(f"  {cat}: エラー {e}", flush=True)

print(f"\nプローブ候補: {len(PROBE_CATS)}件", flush=True)
for cat in PROBE_CATS:
    try:
        r = session.get(f"{BASE_URL}/category/{cat}", timeout=15)
        items = re.findall(r'class="product-item"', r.text)
        if r.ok and items:
            title = re.search(r'<title>([^<]+)', r.text)
            title_text = title.group(1) if title else "(タイトルなし)"
            print(f"  ✓ {cat}: {len(items)}件 — {title_text}", flush=True)
        else:
            print(f"  - {cat}: {r.status_code}", flush=True)
        time.sleep(2)
    except Exception as e:
        print(f"  ! {cat}: エラー {e}", flush=True)
        time.sleep(5)
