"""向量索引：從 normalized.jsonl 建 out/vectors.db，並提供 dense 檢索。

設計取捨：
- embedding 一律以 float32 BLOB 存在 chunks 表 → 單一檔案、可攜、numpy 暴力
  cosine 永遠能跑（數千 chunk 下 <10ms，毫無痛感）。
- 若環境裝得起 sqlite-vec（vec0），額外建一張 ANN 表加速；裝不起就自動退回
  numpy。兩條路徑都用「normalize 後的向量」，故 L2 最近鄰 == cosine 最大相似。

與 archive.db 解耦：向量索引可獨立重建，不動全文檢索那套。
"""

from __future__ import annotations

import os
import sqlite3
import time as _time

import numpy as np

from .embed import Chunk, Embedder, DEFAULT_MODEL, chunk_all
from .schema import read_jsonl

_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE chunks (
    id         INTEGER PRIMARY KEY,
    conv_id    TEXT NOT NULL,
    platform   TEXT NOT NULL,
    title      TEXT,
    time       REAL,
    msg_start  INTEGER NOT NULL,
    msg_end    INTEGER NOT NULL,
    text       TEXT NOT NULL,
    embedding  BLOB NOT NULL
);
CREATE INDEX idx_chunks_conv ON chunks(conv_id);
"""

# 進程內快取：(mtime) -> (ids ndarray, matrix ndarray)，避免每次查詢重讀整庫
_matrix_cache: dict[str, tuple] = {}


def _try_load_vec(con: sqlite3.Connection) -> bool:
    """嘗試載入 sqlite-vec 擴充；成功回 True。"""
    try:
        import sqlite_vec  # type: ignore
        con.enable_load_extension(True)
        sqlite_vec.load(con)
        con.enable_load_extension(False)
        return True
    except Exception:
        return False


def _pack(vec: np.ndarray) -> bytes:
    return np.asarray(vec, dtype="float32").tobytes()


def build(jsonl_path: str, db_path: str, model_name: str = DEFAULT_MODEL,
          batch_size: int = 32) -> dict:
    """(重)建向量索引；冪等：整庫重寫。回傳統計。"""
    chunks: list[Chunk] = list(chunk_all(read_jsonl(jsonl_path)))
    if not chunks:
        raise SystemExit(f"{jsonl_path} 沒有可用內容；請先 ingest")

    embedder = Embedder(model_name)
    print(f"  載入模型 {model_name}（device: {embedder.device_str}）"
          f"並向量化 {len(chunks)} 個 chunk…")
    vecs = embedder.encode([c.text for c in chunks], batch_size=batch_size,
                           show_progress=True)
    dim = int(vecs.shape[1])

    con = sqlite3.connect(db_path)
    try:
        con.executescript(
            "DROP TABLE IF EXISTS vec_chunks;"
            "DROP TABLE IF EXISTS chunks;"
            "DROP TABLE IF EXISTS meta;"
        )
        con.executescript(_SCHEMA)
        con.executemany(
            "INSERT INTO chunks(id, conv_id, platform, title, time, "
            "msg_start, msg_end, text, embedding) VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (i, c.conv_id, c.platform, c.title, c.time,
                 c.msg_start, c.msg_end, c.text, _pack(vecs[i]))
                for i, c in enumerate(chunks)
            ],
        )

        has_vec = _try_load_vec(con)
        if has_vec:
            con.execute(
                f"CREATE VIRTUAL TABLE vec_chunks USING vec0("
                f"embedding float[{dim}])"
            )
            con.executemany(
                "INSERT INTO vec_chunks(rowid, embedding) VALUES (?, ?)",
                [(i, _pack(vecs[i])) for i in range(len(chunks))],
            )

        meta = {
            "model": model_name,
            "dim": str(dim),
            "n_chunks": str(len(chunks)),
            "n_convs": str(len({c.conv_id for c in chunks})),
            "backend": "sqlite-vec" if has_vec else "numpy",
            "built_at": str(int(_time.time())),
        }
        con.executemany("INSERT INTO meta(key, value) VALUES (?, ?)",
                        list(meta.items()))
        con.commit()
    finally:
        con.close()

    _matrix_cache.clear()
    return {"n_chunks": len(chunks), "dim": dim,
            "n_convs": int(meta["n_convs"]), "backend": meta["backend"]}


def get_meta(db_path: str) -> dict:
    con = sqlite3.connect(db_path)
    try:
        return dict(con.execute("SELECT key, value FROM meta").fetchall())
    finally:
        con.close()


def _load_matrix(db_path: str) -> tuple[np.ndarray, np.ndarray]:
    """讀全庫 embedding 成矩陣（含 mtime 快取）。回傳 (ids, matrix)。"""
    key = f"{db_path}:{os.path.getmtime(db_path)}"
    if key in _matrix_cache:
        return _matrix_cache[key]
    con = sqlite3.connect(db_path)
    try:
        rows = con.execute("SELECT id, embedding FROM chunks ORDER BY id").fetchall()
    finally:
        con.close()
    ids = np.array([r[0] for r in rows], dtype="int64")
    mat = np.stack([np.frombuffer(r[1], dtype="float32") for r in rows]) \
        if rows else np.empty((0, 0), dtype="float32")
    _matrix_cache.clear()
    _matrix_cache[key] = (ids, mat)
    return ids, mat


def _fetch_chunks(db_path: str, id_scores: list[tuple[int, float]]) -> list[dict]:
    """依 (id, score) 取回 chunk 列，保留傳入順序。"""
    if not id_scores:
        return []
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        ids = [i for i, _ in id_scores]
        q = ("SELECT id, conv_id, platform, title, time, msg_start, msg_end, "
             f"text FROM chunks WHERE id IN ({','.join('?' * len(ids))})")
        by_id = {r["id"]: dict(r) for r in con.execute(q, ids).fetchall()}
    finally:
        con.close()
    out = []
    for i, score in id_scores:
        row = by_id.get(i)
        if row is not None:
            row["score"] = score
            out.append(row)
    return out


def search(db_path: str, query_vec: np.ndarray, top_k: int = 8) -> list[dict]:
    """dense 檢索：回傳 top_k chunk（含 score=cosine 相似度，越大越近）。

    query_vec 須為已 normalize 的向量（Embedder 預設如此）。
    """
    q = np.asarray(query_vec, dtype="float32").ravel()

    con = sqlite3.connect(db_path)
    has_vec_table = False
    try:
        has_vec_table = bool(con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='vec_chunks'"
        ).fetchone())
        if has_vec_table and _try_load_vec(con):
            rows = con.execute(
                "SELECT rowid, distance FROM vec_chunks "
                "WHERE embedding MATCH ? ORDER BY distance LIMIT ?",
                (_pack(q), top_k),
            ).fetchall()
            # vec0 預設 L2 距離；normalize 向量下 cosine = 1 - L2^2/2
            id_scores = [(int(r), 1.0 - (float(d) ** 2) / 2.0) for r, d in rows]
            return _fetch_chunks(db_path, id_scores)
    except Exception:
        pass  # vec 路徑失敗就退回 numpy
    finally:
        con.close()

    # numpy 暴力 cosine（normalize 向量 → 點積即 cosine）
    ids, mat = _load_matrix(db_path)
    if mat.size == 0:
        return []
    sims = mat @ q
    k = min(top_k, sims.shape[0])
    top = np.argpartition(-sims, k - 1)[:k]
    top = top[np.argsort(-sims[top])]
    id_scores = [(int(ids[t]), float(sims[t])) for t in top]
    return _fetch_chunks(db_path, id_scores)
