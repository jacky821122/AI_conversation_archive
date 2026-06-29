"""ai_archive CLI — Phase A 地基指令。

  python -m ai_archive.cli ingest            # 解析三家 → normalized.jsonl + archive.db
  python -m ai_archive.cli list              # 對話清單（可 --json）
  python -m ai_archive.cli get "<conv_id>"   # 取單段對話全文（可 --json）
  python -m ai_archive.cli search "<關鍵字>"  # 純全文檢索（中文可用）
  python -m ai_archive.cli stats             # 顯示資料庫統計
"""

from __future__ import annotations

import argparse
import json
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
    if getattr(args, "claude_path", None):
        os.environ["CLAUDE_PROJECTS"] = os.path.abspath(
            os.path.expanduser(args.claude_path))
    if getattr(args, "claude_exclude_prompts", None):
        os.environ["CLAUDE_EXCLUDE_PROMPTS"] = args.claude_exclude_prompts
    jsonl = os.path.join(args.out, "normalized.jsonl")
    db = os.path.join(args.out, "archive.db")

    platforms = args.platforms or list(REGISTRY)
    convs = list(parse_all(args.data, platforms))
    n = write_jsonl(convs, jsonl)  # raw fragments，永不被 overlay 改寫

    # overlay：若已有 threads.json，把 Gemini fragment 合併成 session 再建庫
    from . import stitch
    view = stitch.apply_threads(convs, args.out)
    threaded = len(view) != len(convs)
    st = store.build(iter(view), db)

    print(f"✓ 正規化 {n} 段對話（raw）→ {jsonl}")
    if threaded:
        print(f"✓ 套用 Gemini session 還原（threads.json）→ {len(view)} 段")
    print(f"✓ 建立資料庫 → {db}")
    print(f"  訊息數: {st['messages']}")
    print("  各平台對話數:")
    for p, c in sorted(st["per_platform"].items()):
        print(f"    {p:<10} {c}")


def cmd_search(args) -> None:
    db = os.path.join(args.out, "archive.db")
    rows = store.search(db, args.query, limit=args.limit)
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


def cmd_list(args) -> None:
    """對話清單：list / filter（platform、month）/ order，預設人讀，--json 給 agent。"""
    db = os.path.join(args.out, "archive.db")
    items = store.list_conversations(db, platform=args.platform, month=args.month,
                                     order=args.order, limit=args.limit,
                                     offset=args.offset)
    total = store.count_conversations(db, platform=args.platform, month=args.month)
    if args.json:
        print(json.dumps(
            {"platform": args.platform, "month": args.month, "order": args.order,
             "limit": args.limit, "offset": args.offset,
             "total": total, "count": len(items), "items": items},
            ensure_ascii=False))
        return
    if not items:
        print("（無對話）")
        return
    for c in items:
        print(f"[{c['platform']:<7} {_fmt_time(c['create_time'])}] "
              f"msgs={c['n_messages']:<4} {c['title'] or '（無標題）'}")
        print(f"    └ {c['id']}")
    shown = args.offset + len(items)
    print(f"— 顯示 {args.offset + 1}–{shown} / 共 {total} 段 —")


def cmd_get(args) -> None:
    """取單段對話全文：meta + 全部訊息。預設人讀，--json 給 agent。"""
    db = os.path.join(args.out, "archive.db")
    conv = store.get_conversation(db, args.conv_id)
    if conv is None:
        raise SystemExit(f"查無對話 {args.conv_id}")
    if args.json:
        print(json.dumps(conv, ensure_ascii=False))
        return
    print(f"[{conv['platform']}] {conv['title'] or '（無標題）'}")
    print(f"  建立 {_fmt_time(conv['create_time'])} / 更新 "
          f"{_fmt_time(conv['update_time'])} / {conv['n_messages']} 則訊息")
    print(f"  id: {conv['id']}")
    print()
    for m in conv["messages"]:
        print(f"#{m['idx']} {m['role']} [{_fmt_time(m['time'])}]")
        print(m["text"])
        atts = m.get("attachments") or []
        if atts:
            print(f"📎 {len(atts)} 個附件: {', '.join(atts)}")
        print()


def cmd_stats(args) -> None:
    db = os.path.join(args.out, "archive.db")
    st = store.stats(db)
    print(f"對話總數: {st['conversations']}")
    print(f"訊息總數: {st['messages']}")
    print("各平台:", dict(st["per_platform"]))
    print("各角色:", dict(st["roles"]))


def cmd_index(args) -> None:
    from . import index, stitch
    from .schema import read_jsonl
    os.makedirs(args.out, exist_ok=True)
    jsonl = os.path.join(args.out, "normalized.jsonl")
    if not os.path.exists(jsonl):
        raise SystemExit(f"找不到 {jsonl}；請先執行 ingest")
    vdb = os.path.join(args.out, "vectors.db")
    # overlay：有 threads.json 就用還原後的 session 來分塊/向量化
    convs = stitch.apply_threads(read_jsonl(jsonl), args.out)
    st = index.build(jsonl, vdb, model_name=args.model, batch_size=args.batch_size,
                     conversations=convs)
    print(f"✓ 建立向量索引 → {vdb}")
    print(f"  chunk 數: {st['n_chunks']} (來自 {st['n_convs']} 段對話)")
    print(f"  維度: {st['dim']} | 後端: {st['backend']}")


def cmd_search_dense(args) -> None:
    """語意（dense）檢索：不花 API 錢，純看本地向量檢索品質。"""
    from . import index
    from .embed import Embedder
    vdb = os.path.join(args.out, "vectors.db")
    if not os.path.exists(vdb):
        raise SystemExit(f"找不到 {vdb}；請先執行 index")
    meta = index.get_meta(vdb)
    qvec = Embedder(meta.get("model", "BAAI/bge-m3")).encode_one(args.query)
    rows = index.search(vdb, qvec, top_k=args.limit)
    if not rows:
        print("（無命中）")
        return
    for r in rows:
        snippet = r["text"].replace("\n", " ")
        if len(snippet) > 140:
            snippet = snippet[:140] + "…"
        print(f"[{r['score']:.3f}] [{r['platform']:<7} {_fmt_time(r['time'])}] "
              f"{r['title']}")
        print(f"    {snippet}")
        print(f"    └ {r['conv_id']} #msg {r['msg_start']}–{r['msg_end']}")


def cmd_ask(args) -> None:
    """混合檢索 → Claude 作答附出處（會送檢索片段到 API）。"""
    from . import rag
    res = rag.ask(args.question, out_dir=args.out,
                  model=args.model, top_k=args.top_k)
    print(res["answer"])
    print()
    print(f"— 出處（{res['model']}）—")
    for s in res["sources"]:
        print(f"  [{s['n']}] {s['platform']:<7} {_fmt_time(s['time'])} "
              f"{s['title'] or '（無標題）'}")
        print(f"      └ {s['conv_id']} #msg {s['msg_start']}–{s['msg_end']}")


def _parse_date(s: str | None) -> float | None:
    """YYYY-MM-DD（本地時區）→ epoch 秒。"""
    if not s:
        return None
    dt = datetime.strptime(s, "%Y-%m-%d").astimezone()
    return dt.timestamp()


def cmd_stitch(args) -> None:
    """Gemini 對話串本地還原（產 out/threads.json，不動其他資料）。"""
    from . import stitch
    since, until = _parse_date(args.since), _parse_date(args.until)

    if args.report:
        print(stitch.report(args.out))
        return
    if args.dump_slice:
        print(stitch.dump_slice(args.out, since, until))
        return
    if args.eval:
        m = stitch.evaluate(args.out, args.eval, since, until)
        print(f"已標 fragment: {m['n_labeled']}（gold {m['n_gold_threads']} 串）")
        print(f"連結 precision: {m['precision']:.3f}  recall: {m['recall']:.3f}  "
              f"f1: {m['f1']:.3f}")
        print(f"過併 pair: {m['over_merge_pairs']}  漏併 pair: {m['under_merge_pairs']}")
        return

    if args.method == "timegap":
        res = stitch.build_timegap(out_dir=args.out, gap_min=args.gap_min)
        print(f"✓ {res['n_fragments']} fragment → {res['n_threads']} 串 → {res['path']}")
        print(f"  方法: 時間 gap（門檻 {args.gap_min} 分，deterministic、零 LLM）")
        return

    res = stitch.build(out_dir=args.out, model=args.model,
                       window=args.window, top_k=args.top_k,
                       sim_hi=args.sim_hi, sim_med=args.sim_med, sim_lo=args.sim_lo)
    st = res["stats"]
    print(f"✓ {res['n_fragments']} fragment → {res['n_threads']} 串 → {res['path']}")
    print(f"  規則自動接 {st['rule_link']} / 自動拒 {st['rule_new']}")
    print(f"  LLM 審判 {st['llm_calls']} 次（快取命中 {st['cache_hits']}）"
          f"→ 接 {st['llm_link']} / 拒 {st['llm_new']}")


def cmd_web(args) -> None:
    # 以環境變數把 db 路徑傳給 api.py，再啟動 uvicorn
    os.environ["AI_ARCHIVE_DB"] = os.path.abspath(
        os.path.join(args.out, "archive.db"))
    try:
        import uvicorn
    except ImportError:
        raise SystemExit(
            "需要 web 依賴：pip install -r requirements-web.txt")
    print(f"資料庫: {os.environ['AI_ARCHIVE_DB']}")
    print(f"啟動 web 介面 → http://{args.host}:{args.port}")
    uvicorn.run("ai_archive.api:app", host=args.host, port=args.port,
                reload=args.reload)


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="ai_archive")
    p.add_argument("--data", default=_DEFAULT_DATA, help="原始匯出資料夾 (預設: data)")
    p.add_argument("--out", default=_DEFAULT_OUT, help="輸出資料夾 (預設: out)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("ingest", help="解析四家 → normalized.jsonl + archive.db")
    pi.add_argument("--platforms", nargs="*", choices=list(REGISTRY),
                    help="只處理指定平台 (預設全部)")
    pi.add_argument("--claude-path", default=None,
                    help="Claude Code 紀錄根目錄 (預設 ~/.claude/projects)")
    pi.add_argument("--claude-exclude-prompts", default=None,
                    help="逗號分隔的首則 user 訊息前綴；命中者視為 headless "
                         "噪音(cron/ping)丟棄 (也可用 CLAUDE_EXCLUDE_PROMPTS 環境變數)")
    pi.set_defaults(func=cmd_ingest)

    ps = sub.add_parser("search", help="全文檢索")
    ps.add_argument("query")
    ps.add_argument("--limit", type=int, default=10)
    ps.set_defaults(func=cmd_search)

    pl = sub.add_parser("list", help="對話清單 (list/filter/order，唯讀，可 --json)")
    pl.add_argument("--platform", choices=list(REGISTRY),
                    help="只列指定平台 (預設全部)")
    pl.add_argument("--month", help="只列某月 YYYY-MM (依 create_time，本地時區)")
    pl.add_argument("--order", choices=["recent", "oldest"], default="recent",
                    help="排序 (預設 recent)")
    pl.add_argument("--limit", type=int, default=30)
    pl.add_argument("--offset", type=int, default=0, help="分頁起點")
    pl.add_argument("--json", action="store_true", help="輸出 JSON (給 agent 解析)")
    pl.set_defaults(func=cmd_list)

    pg = sub.add_parser("get", help="取單段對話全文 (唯讀，可 --json)")
    pg.add_argument("conv_id", help="對話 id (list/search 結果的 └ 那一行)")
    pg.add_argument("--json", action="store_true", help="輸出 JSON (給 agent 解析)")
    pg.set_defaults(func=cmd_get)

    pt = sub.add_parser("stats", help="資料庫統計")
    pt.set_defaults(func=cmd_stats)

    px = sub.add_parser("index", help="建向量索引 (Phase B，本地 bge-m3)")
    px.add_argument("--model", default="BAAI/bge-m3")
    px.add_argument("--batch-size", type=int, default=32)
    px.set_defaults(func=cmd_index)

    pv = sub.add_parser("search-dense", help="語意檢索 (本地向量，不花 API)")
    pv.add_argument("query")
    pv.add_argument("--limit", type=int, default=8)
    pv.set_defaults(func=cmd_search_dense)

    pa = sub.add_parser("ask", help="RAG 問答（本地檢索 → LLM 作答附出處）")
    pa.add_argument("question")
    pa.add_argument("--model", default=None,
                    help="生成模型 (預設讀 .env 的 AGNES_MODEL，agnes-2.0-flash)")
    pa.add_argument("--top-k", type=int, default=8, help="餵給 LLM 的片段數")
    pa.set_defaults(func=cmd_ask)

    pst = sub.add_parser("stitch", help="Gemini 對話串本地還原 (產 out/threads.json)")
    pst.add_argument("--report", action="store_true", help="印人讀提案（讀現有 threads.json）")
    pst.add_argument("--dump-slice", action="store_true", help="印時間切片 fragment 供標 gold")
    pst.add_argument("--eval", metavar="GOLD", help="用 gold 檔算連結 precision/recall")
    pst.add_argument("--since", help="切片起 YYYY-MM-DD（含）")
    pst.add_argument("--until", help="切片迄 YYYY-MM-DD（不含）")
    pst.add_argument("--method", choices=["timegap", "semantic"], default="timegap",
                     help="timegap=時間 gap 切 session（預設、零 LLM）；semantic=embedding+LLM")
    pst.add_argument("--gap-min", type=float, default=60.0,
                     help="timegap 門檻：相鄰 gap 超過幾分鐘算新 session（預設 60，寧漏不過）")
    pst.add_argument("--model", default=None, help="LLM 審判模型（預設 .env 的 AGNES_MODEL）")
    pst.add_argument("--window", type=int, default=12, help="候選 recency window")
    pst.add_argument("--top-k", type=int, default=6, help="每段保留候選數")
    pst.add_argument("--sim-hi", type=float, default=0.75)
    pst.add_argument("--sim-med", type=float, default=0.60)
    pst.add_argument("--sim-lo", type=float, default=0.45)
    pst.set_defaults(func=cmd_stitch)

    pw = sub.add_parser("web", help="啟動 localhost web 查找介面")
    pw.add_argument("--host", default="127.0.0.1")
    pw.add_argument("--port", type=int, default=8765)
    pw.add_argument("--reload", action="store_true", help="開發用熱重載")
    pw.set_defaults(func=cmd_web)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
