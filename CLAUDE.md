# AI Conversation Archive — 專案說明

把個人的 ChatGPT / Grok / Gemini 對話匯出，做成可搜尋、可問答的語料庫與第二大腦。

## ⚠️ 開工前先讀進度檔

**專案的計畫、進度、決策脈絡在 `PLAN.local.md`（gitignored，本機才有）。每個 session 開始處理本專案前，先讀 `PLAN.local.md`** — 它是 source of truth，記錄了「為什麼這樣做、接下來的路線、踩過的坑」，git log 只記「改了什麼」。若該檔不存在（例如別台機器 clone），以 git log + 本檔的架構說明接續，並提醒使用者。

## 架構

```
ai_archive/
  schema.py        # Conversation / Message dataclass + JSONL 讀寫
  parsers/         # 四家 parser（chatgpt/grok/gemini/claude）+ registry
  store.py         # SQLite + FTS5(trigram) 全文檢索；search() 支援 phrase/or 模式
  embed.py         # bge-m3 本地向量化 + 對話分塊（強制 HF_HUB_OFFLINE）
  index.py         # 建 out/vectors.db（float32 BLOB + 選配 sqlite-vec）+ dense 檢索
  rag.py           # 混合檢索（dense+FTS，RRF）→ 生成端作答附出處
  stitch.py        # Gemini session 還原（時間 gap 切 session）→ threads.json + overlay
  api.py           # FastAPI 後端，serve web/dist
  cli.py           # ingest / search / stats / index / search-dense / ask / stitch / web
web/               # Vite + React + TS 前端（dist 為 build 產物）
deploy/            # systemd 服務（port 2448）
```

## 慣例與邊界

- **隱私邊界**：索引/向量化/檢索全在本地、零外連；只有 RAG 最終「檢索到的片段」會送生成端。`data/`、`out/`、`.env`、`PLAN.local.md` 皆 gitignored。GitHub repo 為 **public，只推程式碼**。
- **依賴分層**：地基純 stdlib；web 用 `requirements-web.txt`；RAG 用 `requirements-rag.txt`。
- **生成端**：RAG 走 OpenAI 相容介面，設定全在 `.env`（見 `.env.example`）。換模型/供應商＝改 `.env`，不動程式。
- **Claude Code 紀錄**：第四平台 `claude`。直接讀本機 `~/.claude/projects/<cwd>/<sessionId>.jsonl`（一檔=一 session），不經 `data/`；可用 `ingest --claude-path <dir>` 或 `CLAUDE_PROJECTS` 環境變數覆蓋。prose only（只留 text，丟 thinking/tool_use/tool_result），一 session 一對話、丟掉無 user 文字的 trivial session。`id=claude:<sessionId>`，冪等。
- **中文檢索**：FTS5 用 trigram tokenizer（連續中文可比對）。
- **Gemini session 還原**：Gemini 匯出無 thread 資訊、被切成 1問1答。`stitch` 用時間 gap（預設 60 分）把連續坐席還原成 session，產 `out/threads.json`。`normalized.jsonl` 永保 raw fragment；`ingest`/`index` 在**消費端**自動套 overlay（有 threads.json 就把 Gemini fragment 合併成 session），故 archive.db/vectors.db/web/stats 都反映 session（Gemini 394→173），原始資料不被改寫。
- **冪等**：`ingest` / `index` / `stitch` 重跑覆蓋輸出、結果一致。
- **GPU**：本機有 NVIDIA GPU（WSL），bge-m3 自動走 cuda。

## 常用指令

```
python -m ai_archive.cli ingest          # 解析三家 → normalized.jsonl + archive.db
python -m ai_archive.cli stitch          # Gemini session 還原 → out/threads.json
python -m ai_archive.cli index           # 建向量索引 out/vectors.db
python -m ai_archive.cli search "<關鍵字>" # 全文檢索
python -m ai_archive.cli ask "<問題>"     # RAG 問答（本地檢索 → 生成端附出處）
python -m ai_archive.cli web             # 啟動 localhost web 介面
```

完整刷新順序（含 Gemini 還原）：`ingest`（產 raw jsonl）→ `stitch`（產 threads.json）→
`ingest`（archive.db 套 overlay）→ `index`（vectors.db 套 overlay）。`stitch` 細節／驗證
（`--report` / `--dump-slice` / `--eval`）見 `PLAN.local.md` Phase D。
