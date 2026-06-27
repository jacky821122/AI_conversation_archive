"""SQLite 儲存 + 中文可用的全文檢索。

- conversations / messages 兩張表存正規化結果。
- messages_fts 用 FTS5 trigram tokenizer（內建、無依賴）——預設 unicode61
  對連續中文切不開、完全比不到。trigram 僅支援 ≥3 字查詢，故 search() 對
  <3 字 query 自動退回 LIKE 全表掃描。
"""

from __future__ import annotations

import json
import math
import sqlite3
from typing import Iterable

from .schema import Conversation

_SCHEMA = """
CREATE TABLE conversations (
    id          TEXT PRIMARY KEY,
    platform    TEXT NOT NULL,
    title       TEXT,
    create_time REAL,
    update_time REAL,
    n_messages  INTEGER NOT NULL
);
CREATE TABLE messages (
    rowid    INTEGER PRIMARY KEY,
    conv_id  TEXT NOT NULL REFERENCES conversations(id),
    idx      INTEGER NOT NULL,
    role     TEXT NOT NULL,
    text     TEXT NOT NULL,
    time     REAL,
    tokens   INTEGER NOT NULL DEFAULT 0,
    attachments TEXT NOT NULL DEFAULT '[]'  -- JSON list[str]：附件指標（asset_pointer），Tier 0 只留線索不解析本體
);
CREATE INDEX idx_messages_conv ON messages(conv_id);
CREATE VIRTUAL TABLE messages_fts USING fts5(
    text,
    content='messages',
    content_rowid='rowid',
    tokenize='trigram'
);
"""


def build(convs: Iterable[Conversation], db_path: str) -> dict:
    """(重) 建資料庫；冪等：每次重建。回傳統計。"""
    con = sqlite3.connect(db_path)
    try:
        con.executescript(
            "DROP TABLE IF EXISTS messages_fts;"
            "DROP TABLE IF EXISTS messages;"
            "DROP TABLE IF EXISTS conversations;"
        )
        con.executescript(_SCHEMA)
        n_conv = 0
        n_msg = 0
        per_platform: dict[str, int] = {}
        for c in convs:
            con.execute(
                "INSERT INTO conversations VALUES (?,?,?,?,?,?)",
                (c.id, c.platform, c.title, c.create_time, c.update_time,
                 len(c.messages)),
            )
            for i, m in enumerate(c.messages):
                con.execute(
                    "INSERT INTO messages(conv_id, idx, role, text, time, tokens, "
                    "attachments) VALUES (?,?,?,?,?,?,?)",
                    (c.id, i, m.role, m.text, m.time, estimate_tokens(m.text),
                     json.dumps(m.attachments, ensure_ascii=False)),
                )
                n_msg += 1
            n_conv += 1
            per_platform[c.platform] = per_platform.get(c.platform, 0) + 1
        # 用 messages 內容回填 FTS（external content table 模式）
        con.execute(
            "INSERT INTO messages_fts(rowid, text) SELECT rowid, text FROM messages"
        )
        con.commit()
        return {"conversations": n_conv, "messages": n_msg,
                "per_platform": per_platform}
    finally:
        con.close()


import re

# 抽 token：ASCII 英數 run（≥2）+ CJK run（≥3，trigram 下限）
_ASCII_RE = re.compile(r"[A-Za-z0-9]{2,}")
_CJK_RE = re.compile(r"[一-鿿぀-ヿ]{3,}")

# token 估算用 CJK 類（與檢索用 _CJK_RE 同範圍：中日漢字＋假名）。
_TOKEN_CJK_RE = re.compile(r"[一-鿿぀-ヿ]")


def estimate_tokens(text: str) -> int:
    """純 stdlib 啟發式 token 估算：CJK 1 字 ≈ 1 token，其餘 4 字元 ≈ 1 token。

    精準度不重要——跨平台、跨 user/assistant 用同一把尺即公平。供時間軸的
    token 視角彙總用。
    """
    if not text:
        return 0
    cjk = len(_TOKEN_CJK_RE.findall(text))
    rest = len(text) - cjk
    return cjk + math.ceil(rest / 4)


def _fts_query(query: str) -> str:
    # 整串當片語，跳脫雙引號，避免 FTS5 語法字元被誤判
    return '"' + query.replace('"', '""') + '"'


def _fts_or_query(query: str) -> str | None:
    """把自然語言問句拆成關鍵詞，組成 OR 片語查詢（給 RAG 混合檢索用）。

    整句片語比對對問句幾乎必 0 命中；改抽英文技術詞 + CJK 片段做 OR，
    讓 FTS 補上 dense 容易稀釋掉的「精確詞命中」（如 pandas、專有名詞）。
    無可用 token 時回 None（退回純 dense）。
    """
    terms = _ASCII_RE.findall(query) + _CJK_RE.findall(query)
    if not terms:
        return None
    return " OR ".join('"' + t.replace('"', '""') + '"' for t in terms)


def search(db_path: str, query: str, platform: str | None = None,
           limit: int = 10, offset: int = 0, mode: str = "phrase") -> list[dict]:
    """回傳命中訊息（含所屬對話脈絡）。

    mode="phrase"（預設，給 web/CLI search）：整句當片語，≥3 字走 FTS5
    trigram、<3 字退回 LIKE。mode="or"（給 RAG）：抽關鍵詞做 OR 檢索。
    platform 可選做平台篩選。
    """
    query = query.strip()
    if not query:
        return []
    match = _fts_or_query(query) if mode == "or" else None
    use_fts = match is not None or (mode == "phrase" and len(query) >= 3)
    if match is None and mode != "or":
        match = _fts_query(query)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    plat_clause = " AND c.platform = ?" if platform else ""
    plat_args: tuple = (platform,) if platform else ()
    try:
        if use_fts:
            rows = con.execute(
                f"""
                SELECT m.conv_id, m.idx, m.role, m.text, m.time,
                       c.platform, c.title
                FROM messages_fts f
                JOIN messages m ON m.rowid = f.rowid
                JOIN conversations c ON c.id = m.conv_id
                WHERE messages_fts MATCH ?{plat_clause}
                ORDER BY bm25(messages_fts)
                LIMIT ? OFFSET ?
                """,
                (match, *plat_args, limit, offset),
            ).fetchall()
        else:
            rows = con.execute(
                f"""
                SELECT m.conv_id, m.idx, m.role, m.text, m.time,
                       c.platform, c.title
                FROM messages m
                JOIN conversations c ON c.id = m.conv_id
                WHERE m.text LIKE ?{plat_clause}
                LIMIT ? OFFSET ?
                """,
                (f"%{query}%", *plat_args, limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def get_conversation(db_path: str, conv_id: str) -> dict | None:
    """回傳整段對話：meta + 全部訊息（依 idx 排序）。"""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        c = con.execute(
            "SELECT id, platform, title, create_time, update_time, n_messages "
            "FROM conversations WHERE id = ?", (conv_id,)
        ).fetchone()
        if c is None:
            return None
        msgs = con.execute(
            "SELECT idx, role, text, time, attachments FROM messages "
            "WHERE conv_id = ? ORDER BY idx", (conv_id,)
        ).fetchall()
        out = dict(c)
        messages = []
        for m in msgs:
            d = dict(m)
            try:
                d["attachments"] = json.loads(d.get("attachments") or "[]")
            except (TypeError, ValueError):
                d["attachments"] = []
            messages.append(d)
        out["messages"] = messages
        return out
    finally:
        con.close()


def _conv_filter(platform: str | None, month: str | None) -> tuple[str, list]:
    """組合 platform / month(YYYY-MM) 的 WHERE 子句。"""
    clauses: list[str] = []
    args: list = []
    if platform:
        clauses.append("platform = ?")
        args.append(platform)
    if month:
        clauses.append(
            "strftime('%Y-%m', create_time, 'unixepoch', 'localtime') = ?")
        args.append(month)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, args


def list_conversations(db_path: str, platform: str | None = None,
                       month: str | None = None, order: str = "recent",
                       limit: int = 30, offset: int = 0) -> list[dict]:
    """對話層級清單（瀏覽 / 最近 / 某月）。order: recent | oldest。"""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    where, args = _conv_filter(platform, month)
    direction = "ASC" if order == "oldest" else "DESC"
    try:
        rows = con.execute(
            f"""
            SELECT id, platform, title, create_time, update_time, n_messages
            FROM conversations
            {where}
            ORDER BY COALESCE(create_time, 0) {direction}
            LIMIT ? OFFSET ?
            """,
            (*args, limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        con.close()


def count_conversations(db_path: str, platform: str | None = None,
                        month: str | None = None) -> int:
    con = sqlite3.connect(db_path)
    where, args = _conv_filter(platform, month)
    try:
        return con.execute(
            f"SELECT count(*) FROM conversations {where}", args
        ).fetchone()[0]
    finally:
        con.close()


def distribution(db_path: str) -> list[dict]:
    """各平台 × 各 YYYY-MM 的對話計數與 token 估算量（給儀表板月份圖）。"""
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute(
            """
            SELECT c.platform,
                   strftime('%Y-%m', c.create_time, 'unixepoch', 'localtime') AS month,
                   count(*) AS n,
                   COALESCE(SUM(mt.tokens), 0) AS tokens
            FROM conversations c
            LEFT JOIN (
                SELECT conv_id, SUM(tokens) AS tokens
                FROM messages GROUP BY conv_id
            ) mt ON mt.conv_id = c.id
            WHERE c.create_time IS NOT NULL
            GROUP BY c.platform, month
            ORDER BY month
            """
        ).fetchall()
        return [{"platform": p, "month": m, "n": n, "tokens": tok}
                for p, m, n, tok in rows]
    finally:
        con.close()


def stats(db_path: str) -> dict:
    con = sqlite3.connect(db_path)
    try:
        nc = con.execute("SELECT count(*) FROM conversations").fetchone()[0]
        nm = con.execute("SELECT count(*) FROM messages").fetchone()[0]
        pp = dict(con.execute(
            "SELECT platform, count(*) FROM conversations GROUP BY platform"
        ).fetchall())
        roles = dict(con.execute(
            "SELECT role, count(*) FROM messages GROUP BY role"
        ).fetchall())
        return {"conversations": nc, "messages": nm,
                "per_platform": pp, "roles": roles}
    finally:
        con.close()
