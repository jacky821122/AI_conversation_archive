# AI Conversation Archive

把 ChatGPT / Grok / Gemini / Claude Code 的對話匯出統一成一份個人語料庫，做成可搜尋、
可問答的第二大腦。兩大目標：

1. **RAG 第二大腦** — 用自然語言問「我之前對 X 的想法」，本地檢索 → 生成端作答附出處。
2. **persona 萃取** — 從海量對話提煉個人語氣／個性／思考模式（規劃中）。

## 隱私邊界

索引／向量化／檢索**全在本地、零外連**；只有 RAG 最終「檢索到的片段」會送生成端。
`data/`、`out/`、`.env` 皆 gitignored，GitHub repo 為 **public，只推程式碼**。

## 資料流

```
data/ (原始匯出)
  ├─ <hash>/conversations-*.json             ChatGPT
  ├─ ttl/30d/…/prod-grok-backend.json        Grok
  └─ Takeout/…/Gemini Apps_JSON/我的活動.json  Gemini
~/.claude/projects/<cwd>/<sessionId>.jsonl    Claude Code（本機直讀，不經 data/）
        │  ingest
        ▼
out/normalized.jsonl   統一格式，一段對話一行（後續所有階段的唯一輸入）
out/archive.db         SQLite + FTS5(trigram) 全文檢索
out/vectors.db         本地 bge-m3 向量索引（語意檢索／RAG）
out/threads.json       Gemini session 還原 overlay
```

## 平台

| 平台 | 來源 | 說明 |
|---|---|---|
| `chatgpt` | `data/**/conversations-*.json` | mapping 樹線性化 |
| `grok` | `data/**/prod-grok-backend.json` | responses → 正規化 |
| `gemini` | `data/**/Gemini Apps_JSON/*.json` | My Activity，1問1答 fragment（見下方 session 還原） |
| `claude` | `~/.claude/projects/<cwd>/<sessionId>.jsonl` | 本機 Claude Code session，一檔一對話，prose only |

新增平台只需在 `ai_archive/parsers/` 加一個模組並註冊，其餘階段不用改。

### Claude Code 紀錄

第四平台 `claude` 直接讀本機 `~/.claude/projects/`（一檔 = 一 session），**不需要倒進
`data/`**。只保留 prose（user + assistant 的 text），丟掉 thinking／tool_use／tool_result；
一個 session 一段對話，丟掉沒有任何 user 文字的 trivial session。`id=claude:<sessionId>`，
冪等。可用 `ingest --claude-path <dir>` 或 `CLAUDE_PROJECTS` 環境變數覆蓋來源路徑。

## 依賴分層

- **地基**（ingest / search / stats）：純 stdlib，零安裝。
- **web**：`pip install -r requirements-web.txt`（FastAPI + uvicorn）。
- **RAG**（index / search-dense / ask）：`pip install -r requirements-rag.txt`
  （sentence-transformers／bge-m3、numpy、openai、python-dotenv）。

## 指令

```bash
python -m ai_archive.cli ingest            # 解析四家 → normalized.jsonl + archive.db
python -m ai_archive.cli stitch            # Gemini session 還原 → out/threads.json
python -m ai_archive.cli index             # 建向量索引 out/vectors.db（需 RAG 依賴）
python -m ai_archive.cli search "<關鍵字>"  # 全文檢索（中文可用）
python -m ai_archive.cli search-dense "<q>" # 語意檢索（本地向量，不花 API）
python -m ai_archive.cli ask "<問題>"       # RAG 問答（本地檢索 → 生成端附出處）
python -m ai_archive.cli stats             # 資料庫統計
python -m ai_archive.cli web               # 啟動 localhost web 介面
```

可選全域旗標 `--data <dir>`（預設 `data`）、`--out <dir>`（預設 `out`）；
`ingest --platforms chatgpt grok`（只處理指定平台）、`ingest --claude-path <dir>`。

完整刷新順序（含 Gemini 還原）：`ingest`（產 raw jsonl）→ `stitch`（產 threads.json）→
`ingest`（archive.db 套 overlay）→ `index`（vectors.db 套 overlay）。

### 統一 schema（`out/normalized.jsonl`）

```jsonc
{
  "id": "chatgpt:<uuid>",        // grok:<uuid> / gemini:<hash> / claude:<sessionId>
  "platform": "chatgpt",
  "title": "...",
  "create_time": 1234567890.0,   // epoch 秒
  "update_time": 1234567890.0,
  "messages": [
    {"role": "user", "text": "...", "time": 1234567890.0, "attachments": []}
  ]
}
```

## 中文檢索

SQLite 預設 tokenizer 對連續中文切不開（連「淡江大橋」都比不到），故 FTS5 改用內建
**trigram** tokenizer。trigram 僅支援 ≥3 字查詢，`search` 對 <3 字 query 自動退回 `LIKE`
全表掃描。語意層的中文檢索由本地 bge-m3 embedding 負責。

## Gemini session 還原

Gemini 匯出無 thread 資訊、被切成 1問1答 fragment。`stitch` 用時間 gap（預設 60 分）把
連續坐席還原成 session，產 `out/threads.json`。`normalized.jsonl` 永保 raw fragment；
`ingest`／`index` 在**消費端**自動套 overlay（有 threads.json 就把 Gemini fragment 合併成
session），故 archive.db／vectors.db／web／stats 都反映 session，原始資料不被改寫。

## RAG 問答（`ask`）

混合檢索：問題經 bge-m3 向量化 → dense top-k；FTS trigram 命中映射回 chunk；兩條 ranked
list 用 RRF 融合。檢索全在本地，只有融合後的片段連同問題送生成端。生成端走 **OpenAI 相容
介面**，base_url／金鑰／模型皆由 `.env` 設定（見 `.env.example`）——換模型／供應商＝改
`.env`，不動程式。

## 程式結構

```
ai_archive/
  schema.py          統一 Conversation / Message + JSONL 讀寫
  parsers/
    __init__.py      registry: platform -> parse_fn（新增平台只動這）
    _util.py         時間解析、citation 清理、HTML 去標籤
    chatgpt.py       mapping 樹線性化
    grok.py          responses → 正規化
    gemini.py        My Activity JSON → 迷你兩則對話
    claude.py        ~/.claude/projects/*.jsonl → session 對話（prose only）
  store.py           SQLite schema + FTS5(trigram) + search/get_conversation/...
  embed.py           bge-m3 本地向量化 + 對話分塊
  index.py           建 out/vectors.db + dense 檢索
  rag.py             混合檢索（dense+FTS, RRF）→ 生成端作答附出處
  stitch.py          Gemini session 還原（時間 gap 切 session）
  api.py             FastAPI：/api/* 端點 + serve 前端 dist
  cli.py             ingest / search / stats / index / search-dense / ask / stitch / web
web/                 Vite + React + TS 前端（dist 為 build 產物，不進 git）
deploy/              systemd 服務（port 2448）
```

## localhost Web 介面

搜尋＋讀全文、平台篩選、瀏覽／最近清單、統計儀表板，外加「圖書館長」RAG 問答。
後端 FastAPI（唯讀讀 `out/archive.db`、`out/vectors.db`），前端 Vite + React + TS。

```bash
# 1) 後端依賴
pip install -r requirements-web.txt
# 2) 前端 build（需 Node）
cd web && npm install && npm run build && cd ..
# 3) 啟動：API + 已 build 前端
python -m ai_archive.cli web          # 預設 http://127.0.0.1:8765
```

資料更新後重跑 `ingest` 即生效（web 唯讀讀同一個 DB）。手動指定位址／port：
`python -m ai_archive.cli web --host 0.0.0.0 --port 2448`。

### 當成常駐服務跑（systemd）

WSL2 已啟用 systemd。一行安裝（會問 sudo 密碼）：

```bash
bash deploy/install-service.sh
```

服務 `ai-archive` 綁 `0.0.0.0:2448`、開機自起、掛了自動重啟：

```bash
systemctl status ai-archive          # 看狀態
systemctl restart ai-archive         # 改程式碼後重啟（改資料只要重跑 ingest）
journalctl -u ai-archive -f          # 看日誌
```

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
| `GET /api/conversations?platform=&order=&limit=&offset=` | 對話清單（瀏覽／最近） |
| `GET /api/conversations/{id}` | 整段對話 |
| `POST /api/ask` | RAG 問答（需 RAG 依賴與 `.env` 生成端設定） |
| `GET /api/model/status` · `POST /api/model/load` · `/api/model/release` | bge-m3 模型生命週期（手動載入／釋放，省記憶體） |

## 接下來

- **persona 萃取**：抽 user 訊息 → 蒸餾個人語氣／思考模式。
- 新平台／新匯出：在 `parsers/` 加一個模組並註冊，重跑 `ingest` 即可。
