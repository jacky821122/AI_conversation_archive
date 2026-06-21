"""ai_archive CLI — Phase A 地基指令。

  python -m ai_archive.cli ingest            # 解析三家 → normalized.jsonl + archive.db
  python -m ai_archive.cli search "<關鍵字>"  # 純全文檢索（中文可用）
  python -m ai_archive.cli stats             # 顯示資料庫統計
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

from . import store
from .parsers import REGISTRY, parse_all
from .schema import write_jsonl

_DEFAULT_DATA = "data"
_DEFAULT_OUT = "out"


def _fmt_time(t: float | None) -> str:
    if not t:
        return "----------"
    return datetime.fromtimestamp(t, tz=timezone.utc).astimezone().strftime("%Y-%m-%d")


def cmd_ingest(args) -> None:
    os.makedirs(args.out, exist_ok=True)
    jsonl = os.path.join(args.out, "normalized.jsonl")
    db = os.path.join(args.out, "archive.db")

    platforms = args.platforms or list(REGISTRY)
    convs = list(parse_all(args.data, platforms))
    n = write_jsonl(convs, jsonl)
    st = store.build(iter(convs), db)

    print(f"✓ 正規化 {n} 段對話 → {jsonl}")
    print(f"✓ 建立資料庫 → {db}")
    print(f"  訊息數: {st['messages']}")
    print("  各平台對話數:")
    for p, c in sorted(st["per_platform"].items()):
        print(f"    {p:<10} {c}")


def cmd_search(args) -> None:
    db = os.path.join(args.out, "archive.db")
    rows = store.search(db, args.query, args.limit)
    if not rows:
        print("（無命中）")
        return
    for r in rows:
        snippet = r["text"].replace("\n", " ")
        if len(snippet) > 120:
            snippet = snippet[:120] + "…"
        print(f"[{r['platform']:<7} {_fmt_time(r['time'])}] {r['title']}")
        print(f"    {r['role']}: {snippet}")
        print(f"    └ {r['conv_id']} #{r['idx']}")


def cmd_stats(args) -> None:
    db = os.path.join(args.out, "archive.db")
    st = store.stats(db)
    print(f"對話總數: {st['conversations']}")
    print(f"訊息總數: {st['messages']}")
    print("各平台:", dict(st["per_platform"]))
    print("各角色:", dict(st["roles"]))


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="ai_archive")
    p.add_argument("--data", default=_DEFAULT_DATA, help="原始匯出資料夾 (預設: data)")
    p.add_argument("--out", default=_DEFAULT_OUT, help="輸出資料夾 (預設: out)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("ingest", help="解析三家 → normalized.jsonl + archive.db")
    pi.add_argument("--platforms", nargs="*", choices=list(REGISTRY),
                    help="只處理指定平台 (預設全部)")
    pi.set_defaults(func=cmd_ingest)

    ps = sub.add_parser("search", help="全文檢索")
    ps.add_argument("query")
    ps.add_argument("--limit", type=int, default=10)
    ps.set_defaults(func=cmd_search)

    pt = sub.add_parser("stats", help="資料庫統計")
    pt.set_defaults(func=cmd_stats)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
