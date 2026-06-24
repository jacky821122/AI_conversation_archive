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

import gc
import os
import threading
import time

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# 載入專案根 .env，讓 ASK_TOKEN / ASK_IDLE_RELEASE_SEC 進 env（GET 端點不需要，
# 但 /api/ask + /api/model/* 要）。dotenv 屬 web 依賴，沒裝就略過。
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from . import store

# 專案根目錄 = 本檔的上上層
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("AI_ARCHIVE_DB", os.path.join(_ROOT, "out", "archive.db"))
DIST_DIR = os.path.join(_ROOT, "web", "dist")

# ask 防護：只擋「燒你 agnes token / 以你名義外呼 / 亂載模型佔 VRAM」，不防資料
# （GET 端點本就唯讀開放）。未設 ASK_TOKEN 則 ask 系列一律 503（未啟用）。
ASK_TOKEN = os.environ.get("ASK_TOKEN")
# 閒置自動釋放：最後一次 ask 後超過此秒數，背景 thread 自動卸載模型還 VRAM。
IDLE_RELEASE_SEC = float(os.environ.get("ASK_IDLE_RELEASE_SEC", "900"))  # 15 分

app = FastAPI(title="AI Conversation Archive", version="0.3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _require_db() -> str:
    if not os.path.exists(DB_PATH):
        raise HTTPException(
            status_code=503,
            detail=f"找不到資料庫 {DB_PATH}；請先執行 `python -m ai_archive.cli ingest`",
        )
    return DB_PATH


# ---- RAG 模型生命週期（手動 load/release + 閒置自動釋放）----
# api.py 啟動仍輕量：torch/bge-m3 只在按下 /api/model/load 後才進 VRAM。
# 一把鎖串起 load/release/ask，避免 release 與進行中的 encode 並發。
# 註：release 只還得了模型權重（~2GB）；CUDA context（幾百 MB）綁 process
# 生命週期，要連它也歸零得 restart service（見 PLAN Phase E）。
_model_lock = threading.Lock()
_embedder = None  # 載入後的 embed.Embedder；None = 未載入
_last_used = 0.0  # 最後一次 ask 的時間戳（給閒置自動釋放）


def _check_token(tok: str | None) -> None:
    if not ASK_TOKEN:
        raise HTTPException(status_code=503, detail="ask 未啟用：server 未設定 ASK_TOKEN")
    if tok != ASK_TOKEN:
        raise HTTPException(status_code=401, detail="ask token 不符")


def _model_load() -> dict:
    global _embedder
    with _model_lock:
        if _embedder is None:
            from .embed import Embedder  # lazy：避免啟動就拉 torch

            e = Embedder()
            _ = e.dim  # 觸發 _load()：真的把權重搬進 VRAM（首次 ~10–20s）
            _embedder = e
        return {"loaded": True, "model": _embedder.model_name,
                "device": _embedder.device_str}


def _model_release() -> dict:
    global _embedder
    with _model_lock:
        _embedder = None
        gc.collect()
        try:
            import torch

            torch.cuda.empty_cache()  # 把模型權重 VRAM 還給 driver
        except Exception:
            pass
        return {"loaded": False}


def _model_status() -> dict:
    e = _embedder
    return {"loaded": e is not None,
            "model": e.model_name if e else None,
            "device": e.device_str if e else None}


def _idle_reaper() -> None:
    """背景 daemon：閒置超過 IDLE_RELEASE_SEC 就自動釋放模型。"""
    while True:
        time.sleep(30)
        if _embedder is not None and _last_used and \
                time.time() - _last_used > IDLE_RELEASE_SEC:
            _model_release()


threading.Thread(target=_idle_reaper, daemon=True).start()


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


# ---- RAG 問答（POST；都在 SPA catch-all 之前定義）----
class AskBody(BaseModel):
    question: str
    top_k: int = 8


@app.get("/api/model/status")
def api_model_status() -> dict:
    return _model_status()


@app.post("/api/model/load")
def api_model_load(x_ask_token: str | None = Header(None)) -> dict:
    _check_token(x_ask_token)
    return _model_load()


@app.post("/api/model/release")
def api_model_release(x_ask_token: str | None = Header(None)) -> dict:
    _check_token(x_ask_token)
    return _model_release()


@app.post("/api/ask")
def api_ask(body: AskBody, x_ask_token: str | None = Header(None)) -> dict:
    global _last_used
    _check_token(x_ask_token)
    _require_db()
    if _embedder is None:
        raise HTTPException(status_code=409, detail="模型未載入，請先開啟（POST /api/model/load）")
    from . import rag  # lazy：模組 import 本身輕（不拉 torch）

    out_dir = os.path.dirname(DB_PATH)  # = .../out，rag 需 vectors.db + archive.db 同目錄
    res = rag.ask(body.question, out_dir=out_dir, top_k=body.top_k,
                  embedder=_embedder)
    _last_used = time.time()
    return res


@app.get("/api/plan")
def api_plan() -> dict:
    """唯讀回傳本機 PLAN.local.md 內容（只供本機 web 檢視）。

    只讀固定檔、不吃參數 → 無 path traversal。別台機器無此檔時 exists=false。
    """
    path = os.path.join(_ROOT, "PLAN.local.md")
    if not os.path.isfile(path):
        return {"exists": False, "content": ""}
    with open(path, encoding="utf-8") as f:
        return {"exists": True, "content": f.read()}


# ---- serve 前端（build 後才掛）----
# index.html 一律 no-cache，讓瀏覽器每次都重新驗證、抓到新 build 引用的 hash 資產
# （否則行動 Safari 會卡在舊的 index.html → 載入舊 JS）。assets 為 hash 檔名，可長快取。
_NO_CACHE = {"Cache-Control": "no-cache, no-store, must-revalidate"}


def _index_response() -> FileResponse:
    return FileResponse(os.path.join(DIST_DIR, "index.html"), headers=_NO_CACHE)


if os.path.isdir(DIST_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(DIST_DIR, "assets")),
              name="assets")

    @app.get("/")
    def _index() -> FileResponse:
        return _index_response()

    @app.get("/{full_path:path}")
    def _spa(full_path: str) -> FileResponse:
        # SPA 前端路由 fallback：非 /api 的都回 index.html
        candidate = os.path.join(DIST_DIR, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate, headers=_NO_CACHE)
        return _index_response()
