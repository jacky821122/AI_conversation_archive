"""RAG 第二大腦：混合檢索（本地 dense + FTS）→ LLM 作答並附出處。

資料外流邊界僅在此：問題在本地向量化、檢索全在本地，只有「檢索到的片段」
連同問題送生成端。生成端走 OpenAI 相容介面，預設打 agnes AI（省），
base_url / 金鑰 / 模型皆由 .env 設定，日後換回 Claude 或別家只需改設定。

混合檢索：
- dense：問題經 bge-m3 向量化 → vectors.db 取 top-k chunk（語意）。
- FTS：archive.db trigram 全文檢索命中的訊息，映射回所屬 chunk（關鍵字）。
- 兩條 ranked list 用 RRF（Reciprocal Rank Fusion）融合，避免分數尺度不一。
"""

from __future__ import annotations

import os
import sqlite3

from . import index, store
from .embed import Embedder

# 生成端設定（OpenAI 相容）。皆可由環境變數覆蓋，預設指向 agnes AI。
DEFAULT_MODEL = os.environ.get("AGNES_MODEL", "agnes-2.0-flash")
DEFAULT_BASE_URL = os.environ.get("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
RRF_K = 60  # RRF 常數，弱化排名靠後者的影響

_SYSTEM = """你是使用者「第二大腦」的問答助手。下面提供的「資料片段」全部出自\
使用者本人過去與各家 AI（ChatGPT／Grok／Gemini）的對話紀錄，是他的想法、語氣與\
知識的存底。

規則：
- 只根據提供的片段回答，用繁體中文。
- 在引用具體內容處標註出處編號，例如 [1]、[2]（對應片段編號）。
- 片段不足以回答時，明說「依現有紀錄無法確定」，不要編造。
- 若使用者問的是「我之前怎麼想／說過什麼」，以第一人稱整理他的觀點。"""


def _fts_chunk_ids(archive_db: str, vectors_db: str, query: str,
                   limit: int) -> list[int]:
    """FTS 命中的訊息映射成所屬 chunk id（保序、去重）。

    用 OR 關鍵詞模式：問句整句片語比對幾乎必 0 命中，抽詞 OR 才能補上
    dense 容易稀釋的精確詞命中（pandas、專有名詞…）。
    """
    rows = store.search(archive_db, query, limit=limit, mode="or")
    if not rows:
        return []
    con = sqlite3.connect(vectors_db)
    seen: set[int] = set()
    out: list[int] = []
    try:
        for r in rows:
            hit = con.execute(
                "SELECT id FROM chunks WHERE conv_id = ? "
                "AND msg_start <= ? AND msg_end >= ? LIMIT 1",
                (r["conv_id"], r["idx"], r["idx"]),
            ).fetchone()
            if hit and hit[0] not in seen:
                seen.add(hit[0])
                out.append(hit[0])
    finally:
        con.close()
    return out


def retrieve(question: str, out_dir: str = "out", top_k: int = 8,
             dense_k: int = 20, fts_k: int = 20) -> list[dict]:
    """混合檢索：回傳融合後 top_k 個 chunk（含 meta），附 rrf 分數。"""
    vectors_db = os.path.join(out_dir, "vectors.db")
    archive_db = os.path.join(out_dir, "archive.db")
    if not os.path.exists(vectors_db):
        raise SystemExit(f"找不到 {vectors_db}；請先 `python -m ai_archive.cli index`")

    meta = index.get_meta(vectors_db)
    qvec = Embedder(meta.get("model", "BAAI/bge-m3")).encode_one(question)
    dense_hits = index.search(vectors_db, qvec, top_k=dense_k)
    dense_ids = [h["id"] for h in dense_hits]
    fts_ids = _fts_chunk_ids(archive_db, vectors_db, question, fts_k)

    # RRF 融合
    scores: dict[int, float] = {}
    for rank, cid in enumerate(dense_ids):
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)
    for rank, cid in enumerate(fts_ids):
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)
    top_ids = sorted(scores, key=lambda c: scores[c], reverse=True)[:top_k]

    by_id = {h["id"]: h for h in dense_hits}
    missing = [c for c in top_ids if c not in by_id]
    if missing:  # FTS 帶進、dense 沒取到的 chunk，補抓 meta
        con = sqlite3.connect(vectors_db)
        con.row_factory = sqlite3.Row
        try:
            q = ("SELECT id, conv_id, platform, title, time, msg_start, "
                 f"msg_end, text FROM chunks WHERE id IN "
                 f"({','.join('?' * len(missing))})")
            for r in con.execute(q, missing).fetchall():
                by_id[r["id"]] = dict(r)
        finally:
            con.close()

    out = []
    for cid in top_ids:
        row = by_id.get(cid)
        if row is not None:
            row = dict(row)
            row["rrf"] = scores[cid]
            out.append(row)
    return out


def complete(messages: list[dict], model: str = DEFAULT_MODEL,
             max_tokens: int = 4096, temperature: float | None = None,
             timeout: float | None = None, max_retries: int = 2) -> str:
    """呼叫 OpenAI 相容生成端（預設 agnes），回傳回覆文字。

    集中處理 .env 載入 / 金鑰 / base_url，供 RAG 作答與 stitch 的 LLM 審判共用。
    這是「私人資料送生成端」的唯一出口；呼叫方須自負只送該送的內容。
    """
    try:
        from dotenv import load_dotenv
        load_dotenv()  # 載入專案根 .env（金鑰/base_url/模型）
    except ImportError:
        pass
    try:
        from openai import OpenAI
    except ImportError:
        raise SystemExit("需要 openai 套件：pip install -r requirements-rag.txt")

    api_key = os.environ.get("AGNES_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("未設定 AGNES_API_KEY（檢索片段才會送生成端；見 .env.example）")
    base_url = os.environ.get("AGNES_BASE_URL", DEFAULT_BASE_URL)

    client_kwargs: dict = {"api_key": api_key, "base_url": base_url,
                           "max_retries": max_retries}
    if timeout is not None:
        client_kwargs["timeout"] = timeout
    client = OpenAI(**client_kwargs)
    kwargs: dict = {"model": model, "max_tokens": max_tokens, "messages": messages}
    if temperature is not None:
        kwargs["temperature"] = temperature
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


def _format_time(t: float | None) -> str:
    if not t:
        return "日期不明"
    from datetime import datetime, timezone
    return datetime.fromtimestamp(t, tz=timezone.utc).astimezone().strftime("%Y-%m-%d")


def build_context(chunks: list[dict]) -> str:
    parts = []
    for i, c in enumerate(chunks, 1):
        head = f"[{i}] {c['platform']} · {_format_time(c.get('time'))} · {c.get('title') or '（無標題）'}"
        parts.append(f"{head}\n{c['text']}")
    return "\n\n---\n\n".join(parts)


def ask(question: str, out_dir: str = "out", model: str = DEFAULT_MODEL,
        top_k: int = 8, max_tokens: int = 4096) -> dict:
    """檢索 → 餵生成端（OpenAI 相容）作答。回傳 {answer, sources, model}。"""
    chunks = retrieve(question, out_dir=out_dir, top_k=top_k)
    if not chunks:
        return {"answer": "依現有紀錄找不到相關內容。", "sources": [], "model": model}

    context = build_context(chunks)
    user_msg = f"資料片段：\n\n{context}\n\n---\n\n問題：{question}"

    answer = complete(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        model=model,
        max_tokens=max_tokens,
    )
    sources = [
        {"n": i, "platform": c["platform"], "title": c.get("title"),
         "time": c.get("time"), "conv_id": c["conv_id"],
         "msg_start": c["msg_start"], "msg_end": c["msg_end"]}
        for i, c in enumerate(chunks, 1)
    ]
    return {"answer": answer, "sources": sources, "model": model}
