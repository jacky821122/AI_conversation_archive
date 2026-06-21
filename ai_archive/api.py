"""FastAPI 後端：對 out/archive.db 做唯讀查詢，並 serve 已 build 的前端。

端點（皆唯讀，重用 store.py）：
  GET /api/stats
  GET /api/search?q=&platform=&limit=&offset=
  GET /api/conversations?platform=&order=&limit=&offset=
  GET /api/conversations/{id}

前端 build 產物若存在 (web/dist) 則掛在根路徑，達成單一指令啟動。
開發模式下 Vite (:5173) 會 proxy /api 到本服務，故開 CORS 方便。
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from . import store

# 專案根目錄 = 本檔的上上層
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("AI_ARCHIVE_DB", os.path.join(_ROOT, "out", "archive.db"))
DIST_DIR = os.path.join(_ROOT, "web", "dist")

app = FastAPI(title="AI Conversation Archive", version="0.2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _require_db() -> str:
    if not os.path.exists(DB_PATH):
        raise HTTPException(
            status_code=503,
            detail=f"找不到資料庫 {DB_PATH}；請先執行 `python -m ai_archive.cli ingest`",
        )
    return DB_PATH


@app.get("/api/stats")
def api_stats() -> dict:
    db = _require_db()
    st = store.stats(db)
    st["distribution"] = store.distribution(db)
    return st


@app.get("/api/search")
def api_search(
    q: str = Query(..., min_length=1),
    platform: str | None = None,
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    db = _require_db()
    results = store.search(db, q, platform=platform, limit=limit, offset=offset)
    return {"query": q, "platform": platform, "count": len(results),
            "results": results}


@app.get("/api/conversations")
def api_conversations(
    platform: str | None = None,
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    order: str = Query("recent", pattern="^(recent|oldest)$"),
    limit: int = Query(30, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    db = _require_db()
    items = store.list_conversations(db, platform=platform, month=month,
                                     order=order, limit=limit, offset=offset)
    total = store.count_conversations(db, platform=platform, month=month)
    return {"platform": platform, "month": month, "order": order,
            "total": total, "count": len(items), "items": items}


@app.get("/api/conversations/{conv_id:path}")
def api_conversation(conv_id: str) -> dict:
    db = _require_db()
    conv = store.get_conversation(db, conv_id)
    if conv is None:
        raise HTTPException(status_code=404, detail=f"查無對話 {conv_id}")
    return conv


# ---- serve 前端（build 後才掛）----
if os.path.isdir(DIST_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST_DIR, "assets")),
              name="assets")

    @app.get("/")
    def _index() -> FileResponse:
        return FileResponse(os.path.join(DIST_DIR, "index.html"))

    @app.get("/{full_path:path}")
    def _spa(full_path: str) -> FileResponse:
        # SPA 前端路由 fallback：非 /api 的都回 index.html
        candidate = os.path.join(DIST_DIR, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(DIST_DIR, "index.html"))
