"""RAG 第二大腦：混合檢索（本地 dense + FTS）→ LLM 作答並附出處。

資料外流邊界僅在此：問題在本地向量化、檢索全在本地，只有「檢索到的片段」
連同問題送生成端。生成端由 RAG_PROVIDER 選擇：
- openai（預設）：OpenAI 相容介面，預設打 agnes AI（省）；設定 AGNES_*。
- anthropic：Anthropic Messages 介面（如企業內部 gateway）；設定 ANTHROPIC_*。
兩者的 base_url / 金鑰 / 模型皆由 .env 設定，換供應商只需改設定。

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

# 生成端設定。DEFAULT_MODEL 是硬編碼 fallback；實際預設模型由
# resolve_default_model() 在呼叫時載入 .env 後解析（依 provider 而定）。
DEFAULT_MODEL = "agnes-2.0-flash"
DEFAULT_BASE_URL = "https://apihub.agnes-ai.com/v1"
# Anthropic provider（如企業內部 gateway）的預設，供未在 .env 覆蓋時 fallback。
DEFAULT_ANTHROPIC_MODEL = "Claude-Sonnet-4.6"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
RRF_K = 60  # RRF 常數，弱化排名靠後者的影響


def _provider() -> str:
    """生成端供應商：openai（預設，agnes 相容）或 anthropic（Messages API）。"""
    return os.environ.get("RAG_PROVIDER", "openai").strip().lower()

_SYSTEM = """你是使用者的資料整理助手。下面提供的「資料片段」全部出自\
使用者本人過去與各家 AI（ChatGPT／Grok／Gemini／Claude Code）的對話紀錄，是他的想法、語氣與\
知識的存底。

規則：
- 只根據提供的片段回答，用台灣繁體中文。
- 在引用具體內容處標註出處編號，例如 [1]、[2]（對應片段編號）。
- 片段不足以回答時，明說「依現有紀錄無法確定」，不要編造。
- 若使用者問的是「我之前怎麼想／說過什麼」，以第一人稱整理他的觀點。"""


def _load_dotenv() -> None:
    """Best-effort load of project .env for RAG-only dependencies."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


def _anthropic_model() -> str:
    """館長作答模型。用專屬 RAG_ANTHROPIC_MODEL，避免撞到 Claude Code shell
    注入的 ANTHROPIC_MODEL（那顆是給 CLI 自己用的，會蓋掉此設定）。"""
    return os.environ.get("RAG_ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)


def resolve_default_model() -> str:
    """Return the default generation model after giving .env a chance to load."""
    _load_dotenv()
    if _provider() == "anthropic":
        return _anthropic_model()
    return os.environ.get("AGNES_MODEL", DEFAULT_MODEL)


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
             dense_k: int = 20, fts_k: int = 20,
             embedder: Embedder | None = None) -> list[dict]:
    """混合檢索：回傳融合後 top_k 個 chunk（含 meta），附 rrf 分數。

    embedder：傳入則共用（long-running server 持一份、避免每次重載模型）；
    不傳則自建一個（CLI one-shot 路徑，跑完即退）。
    """
    vectors_db = os.path.join(out_dir, "vectors.db")
    archive_db = os.path.join(out_dir, "archive.db")
    if not os.path.exists(vectors_db):
        raise SystemExit(f"找不到 {vectors_db}；請先 `python -m ai_archive.cli index`")

    meta = index.get_meta(vectors_db)
    emb = embedder or Embedder(meta.get("model", "BAAI/bge-m3"))
    qvec = emb.encode_one(question)
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


def complete(messages: list[dict], model: str | None = None,
             max_tokens: int = 4096, temperature: float | None = None,
             timeout: float | None = None, max_retries: int = 2) -> str:
    """呼叫生成端，回傳回覆文字。依 RAG_PROVIDER 分派 openai / anthropic。

    集中處理 .env 載入 / 金鑰 / base_url，供 RAG 作答與 stitch 的 LLM 審判共用。
    這是「私人資料送生成端」的唯一出口；呼叫方須自負只送該送的內容。
    """
    _load_dotenv()  # 載入專案根 .env（金鑰/base_url/模型）
    if _provider() == "anthropic":
        return _complete_anthropic(messages, model=model, max_tokens=max_tokens,
                                   temperature=temperature, timeout=timeout,
                                   max_retries=max_retries)
    return _complete_openai(messages, model=model, max_tokens=max_tokens,
                            temperature=temperature, timeout=timeout,
                            max_retries=max_retries)


def _complete_openai(messages: list[dict], model: str | None,
                     max_tokens: int, temperature: float | None,
                     timeout: float | None, max_retries: int) -> str:
    """OpenAI 相容生成端（預設 agnes）。"""
    try:
        from openai import OpenAI
    except ImportError:
        raise SystemExit("需要 openai 套件：pip install -r requirements-rag.txt")

    api_key = os.environ.get("AGNES_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("未設定 AGNES_API_KEY（檢索片段才會送生成端；見 .env.example）")
    base_url = os.environ.get("AGNES_BASE_URL", DEFAULT_BASE_URL)
    resolved_model = model if model is not None else os.environ.get("AGNES_MODEL", DEFAULT_MODEL)

    client_kwargs: dict = {"api_key": api_key, "base_url": base_url,
                           "max_retries": max_retries}
    if timeout is not None:
        client_kwargs["timeout"] = timeout
    client = OpenAI(**client_kwargs)
    kwargs: dict = {"model": resolved_model, "max_tokens": max_tokens, "messages": messages}
    if temperature is not None:
        kwargs["temperature"] = temperature
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content or ""


def _parse_custom_headers(raw: str) -> dict[str, str]:
    """把 ANTHROPIC_CUSTOM_HEADERS 解析成 dict。

    支援 Claude Code 慣用格式：多個 header 以換行分隔，每行 `Name: value`。
    """
    headers: dict[str, str] = {}
    for line in raw.replace("\\n", "\n").splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        name, _, value = line.partition(":")
        name = name.strip()
        if name:
            headers[name] = value.strip()
    return headers


def _anthropic_messages(messages: list[dict]) -> tuple[str | None, list[dict]]:
    """把 OpenAI 風格 messages 轉成 Anthropic Messages：抽出 system，其餘保留。"""
    system_parts: list[str] = []
    converted: list[dict] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if role == "system":
            if content:
                system_parts.append(content)
            continue
        converted.append({"role": role, "content": content})
    system = "\n\n".join(system_parts) if system_parts else None
    return system, converted


def _resolve_ca_bundle() -> str | bool:
    """挑一個 httpx 可用的 CA bundle。

    httpx 預設走 certifi，不認公司 proxy（如 Zscaler）換發的憑證，會 SSL
    CERTIFICATE_VERIFY_FAILED。企業環境慣例是把 root 灌進系統 CA store，故
    優先用系統 bundle（含完整中間層），其次才是環境變數指定的自訂 bundle
    （可能只是缺頂層的片段鏈）。都沒有就回 True 讓 httpx 用 certifi 預設。
    """
    candidates = [
        "/etc/ssl/certs/ca-certificates.crt",   # Debian/Ubuntu 系統 store
        "/etc/pki/tls/certs/ca-bundle.crt",     # RHEL/Fedora 系統 store
        os.environ.get("SSL_CERT_FILE"),
        os.environ.get("REQUESTS_CA_BUNDLE"),
    ]
    for ca in candidates:
        if ca and os.path.exists(ca):
            return ca
    return True


def _complete_anthropic(messages: list[dict], model: str | None,
                        max_tokens: int, temperature: float | None,
                        timeout: float | None, max_retries: int) -> str:
    """Anthropic Messages 生成端（如企業內部 gateway）。用 httpx 直打，免額外依賴。"""
    import httpx

    base_url = os.environ.get("ANTHROPIC_BASE_URL", DEFAULT_ANTHROPIC_BASE_URL).rstrip("/")
    resolved_model = model if model is not None else _anthropic_model()

    headers: dict[str, str] = {
        "anthropic-version": os.environ.get("ANTHROPIC_VERSION", "2023-06-01"),
        "content-type": "application/json",
    }
    headers.update(_parse_custom_headers(os.environ.get("ANTHROPIC_CUSTOM_HEADERS", "")))
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        headers.setdefault("x-api-key", api_key)
    if not api_key and "Ocp-Apim-Subscription-Key" not in headers:
        raise SystemExit(
            "未設定 Anthropic 生成端金鑰（ANTHROPIC_API_KEY 或 "
            "ANTHROPIC_CUSTOM_HEADERS 帶訂閱金鑰）；見 .env.example")

    system, converted = _anthropic_messages(messages)
    payload: dict = {"model": resolved_model, "max_tokens": max_tokens,
                     "messages": converted}
    if system:
        payload["system"] = system
    if temperature is not None:
        payload["temperature"] = temperature

    verify = _resolve_ca_bundle()

    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = httpx.post(f"{base_url}/v1/messages", headers=headers,
                              json=payload, timeout=timeout or 60.0,
                              verify=verify)
            resp.raise_for_status()
            data = resp.json()
            return "".join(
                block.get("text", "")
                for block in data.get("content", [])
                if block.get("type") == "text"
            )
        except httpx.HTTPError as e:
            last_exc = e
            if attempt >= max_retries:
                break
    raise SystemExit(f"Anthropic 生成端請求失敗：{last_exc}")


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


def answer_from_chunks(question: str, chunks: list[dict],
                       model: str | None = None,
                       max_tokens: int = 4096) -> dict:
    """Generate an answer from already-retrieved chunks.

    Long-running callers can retrieve under their own local-model lock, release
    that lock, then call this helper for the outbound generation step.
    """
    resolved_model = model if model is not None else resolve_default_model()
    if not chunks:
        return {"answer": "依現有紀錄找不到相關內容。", "sources": [],
                "model": resolved_model}

    context = build_context(chunks)
    user_msg = f"資料片段：\n\n{context}\n\n---\n\n問題：{question}"

    answer = complete(
        [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_msg},
        ],
        model=resolved_model,
        max_tokens=max_tokens,
    )
    sources = [
        {"n": i, "platform": c["platform"], "title": c.get("title"),
         "time": c.get("time"), "conv_id": c["conv_id"],
         "msg_start": c["msg_start"], "msg_end": c["msg_end"]}
        for i, c in enumerate(chunks, 1)
    ]
    return {"answer": answer, "sources": sources, "model": resolved_model}


def ask(question: str, out_dir: str = "out", model: str | None = None,
        top_k: int = 8, max_tokens: int = 4096,
        embedder: Embedder | None = None) -> dict:
    """檢索 → 餵生成端（OpenAI 相容）作答。回傳 {answer, sources, model}。

    embedder：傳入則沿用（server 持有的常駐模型）；不傳則 retrieve 自建。
    """
    chunks = retrieve(question, out_dir=out_dir, top_k=top_k, embedder=embedder)
    return answer_from_chunks(question, chunks, model=model, max_tokens=max_tokens)
