"""SQLite 儲存 + 中文可用的全文檢索。

- conversations / messages 兩張表存正規化結果。
- messages_fts 用 FTS5 trigram tokenizer（內建、無依賴）——預設 unicode61
  對連續中文切不開、完全比不到。trigram 僅支援 ≥3 字查詢，故 search() 對
  <3 字 query 自動退回 LIKE 全表掃描。
"""

from __future__ import annotations

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
    time     REAL
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
                    "INSERT INTO messages(conv_id, idx, role, text, time) "
                    "VALUES (?,?,?,?,?)",
                    (c.id, i, m.role, m.text, m.time),
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


def _fts_query(query: str) -> str:
    # 整串當片語，跳脫雙引號，避免 FTS5 語法字元被誤判
    return '"' + query.replace('"', '""') + '"'


def search(db_path: str, query: str, limit: int = 10) -> list[dict]:
    """回傳命中訊息（含所屬對話脈絡）。

    ≥3 字用 FTS5 trigram（bm25 排序）；<3 字退回 LIKE 子字串掃描。
    """
    query = query.strip()
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        if len(query) >= 3:
            rows = con.execute(
                """
                SELECT m.conv_id, m.idx, m.role, m.text, m.time,
                       c.platform, c.title
                FROM messages_fts f
                JOIN messages m ON m.rowid = f.rowid
                JOIN conversations c ON c.id = m.conv_id
                WHERE messages_fts MATCH ?
                ORDER BY bm25(messages_fts)
                LIMIT ?
                """,
                (_fts_query(query), limit),
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT m.conv_id, m.idx, m.role, m.text, m.time,
                       c.platform, c.title
                FROM messages m
                JOIN conversations c ON c.id = m.conv_id
                WHERE m.text LIKE ?
                LIMIT ?
                """,
                (f"%{query}%", limit),
            ).fetchall()
        return [dict(r) for r in rows]
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
