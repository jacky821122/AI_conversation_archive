# AI Conversation Archive

把 ChatGPT / Grok / Gemini 的對話匯出統一成一份個人語料庫，最終目標：

1. **RAG 第二大腦** — 用自然語言問「我之前對 X 的想法」。
2. **persona 萃取** — 從海量對話提煉個人語氣/個性/思考模式。

完整規劃見 `~/.claude/plans/harmonic-toasting-scott.md`。

## 現況：Phase A — 地基（已完成）

純 stdlib、零安裝、無 LLM。把三家格式正規化成統一 schema + 中文可用的全文檢索。

```
data/ (原始匯出)
  ├─ 3359e59b…/conversations-*.json          ChatGPT (484)
  ├─ ttl/30d/…/prod-grok-backend.json        Grok    (220, 已濾掉空對話)
  └─ Takeout/…/Gemini Apps_JSON/我的活動.json  Gemini  (394)
        │  ingest
        ▼
out/normalized.jsonl   統一格式，一段對話一行（後續 Phase B/C 的唯一輸入）
out/archive.db         SQLite + FTS5(trigram) 全文檢索
```

### 指令

```bash
python3 -m ai_archive.cli ingest            # 解析三家 → normalized.jsonl + archive.db
python3 -m ai_archive.cli search "<關鍵字>"  # 全文檢索（中文可用）
python3 -m ai_archive.cli stats             # 資料庫統計
```

可選 `--data <dir>`（預設 `data`）、`--out <dir>`（預設 `out`）、
`ingest --platforms chatgpt grok`（只處理指定平台）。

### 統一 schema（`out/normalized.jsonl`）

```jsonc
{
  "id": "chatgpt:<uuid>",        // grok:<uuid> / gemini:<hash>
  "platform": "chatgpt",
  "title": "...",
  "create_time": 1234567890.0,   // epoch 秒
  "update_time": 1234567890.0,
  "messages": [
    {"role": "user", "text": "...", "time": 1234567890.0, "attachments": []}
  ]
}
```

### 中文檢索說明

SQLite 預設 tokenizer 對連續中文切不開（連「淡江大橋」都比不到），故 FTS5 改用
內建 **trigram** tokenizer。trigram 僅支援 ≥3 字查詢，`search` 對 <3 字 query
自動退回 `LIKE` 全表掃描。語意層的中文檢索由後續 Phase B 的本地 embedding 負責。

## 程式結構

```
ai_archive/
  schema.py          統一 Conversation / Message + JSONL 讀寫
  parsers/
    __init__.py      registry: platform -> parse_fn（新增平台只動這）
    _util.py         時間解析、HTML 去標籤
    chatgpt.py       mapping 樹線性化
    grok.py          responses → 正規化
    gemini.py        My Activity JSON → 迷你兩則對話
  store.py           SQLite schema + FTS5(trigram) + search/get_conversation/...
  api.py             FastAPI：/api/* 端點 + serve 前端 dist
  cli.py             ingest / search / stats / web
web/                 Vite + React + TS 前端（dist 為 build 產物，不進 git）
```

## Phase A.5 — localhost Web 查找介面（已完成）

把 CLI 查找變成好用的個人 localhost 網頁：搜尋 + 讀全文、平台篩選、瀏覽/最近清單、統計儀表板。後端 FastAPI（唯讀讀 `out/archive.db`），前端 Vite + React + TS（`web/`）。

### 安裝與啟動

```bash
# 1) 後端依賴（地基本身仍純 stdlib，這是 web 額外的）
pip install -r requirements-web.txt

# 2) 前端 build（需 Node）
cd web && npm install && npm run build && cd ..

# 3) 啟動：API + 已 build 前端，單一指令
python3 -m ai_archive.cli web          # 預設 http://127.0.0.1:8765
```

開瀏覽器到 `http://127.0.0.1:8765` 即可。資料更新後重跑 `ingest` 即生效（web 唯讀讀同一個 DB）。

手動指定位址 / port：`python3 -m ai_archive.cli web --host 0.0.0.0 --port 2448`。

### 當成常駐服務跑（systemd，像 immich 那樣開機自起）

WSL2 已啟用 systemd。一行安裝（會問 sudo 密碼）：

```bash
bash deploy/install-service.sh
```

服務 `ai-archive` 會綁 `0.0.0.0:2448`、開機自起、掛了自動重啟。常用指令：

```bash
systemctl status ai-archive          # 看狀態
systemctl restart ai-archive         # 改程式碼後重啟（改資料只要重跑 ingest，不用重啟）
journalctl -u ai-archive -f          # 看日誌
```

服務檔在 `deploy/ai-archive.service`（改 port/python 路徑後重跑安裝腳本即可）。

> 注意：WSL2 的 distro 只有在 Windows 有觸發時才在跑。要真正「永遠在線」，需確保 WSL 持續運行（例如 Windows 工作排程器於登入時 `wsl` 喚起），並讓你的 tailscale（跑在 Windows）能轉到 WSL 的 2448 port。

### 開發模式（前後端分離、熱重載）

```bash
uvicorn ai_archive.api:app --reload --port 8000   # 後端
cd web && npm run dev                              # 前端 :5173，proxy /api → :8000
```

### API 端點（皆唯讀）

| 端點 | 說明 |
|---|---|
| `GET /api/stats` | 總數、各平台計數、各月份分佈 |
| `GET /api/search?q=&platform=&limit=&offset=` | 訊息層級命中 |
| `GET /api/conversations?platform=&order=&limit=&offset=` | 對話清單（瀏覽/最近） |
| `GET /api/conversations/{id}` | 整段對話 |

## 接下來（尚未做）

- **Phase B**：本地 bge-m3 embedding 向量索引 + Claude 作答（`ask`）。
- **Phase C**：抽 user 訊息 → Claude 蒸餾 persona（`persona`）。
- 兩者皆需 `pip install`（sentence-transformers / anthropic 等）與 `ANTHROPIC_API_KEY`。
- 新平台/新匯出：在 `parsers/` 加一個模組並註冊，重跑 `ingest` 即可。
