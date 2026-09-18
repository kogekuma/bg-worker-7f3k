"""mobile_mix の JAN_MAP（商品名+色 → JAN の共有マスタ）だけを bg-worker に置いたもの。

スクレイパー本体は Scanner 側（VPS cron）で動く。ここでは product_jan_groups.IPHONE_JAN_GROUPS の
元データとして mobile_ichiban が参照する。Scanner の scrapers/mobile_mix/jan_map.py と同一内容を
保つこと（更新時は両リポジトリにコピー）。
"""
