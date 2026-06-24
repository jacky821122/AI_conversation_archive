# AI Conversation Archive — 使用手冊

把 ChatGPT / Grok / Gemini / Claude Code 的對話匯出統一成一份個人語料庫，做成可搜尋、
可問答的第二大腦。

> 本檔是**操作手冊**（怎麼建置、怎麼跑）。專案架構與設計原理見 `ARCHITECTURE.md`；
> 本機開發計畫與脈絡見 `PLAN.local.md`。

## 初始建置

```bash
# 1) 地基（ingest / search / stats）：純 stdlib，不用裝任何東西，直接能跑。

# 2) web 介面依賴
pip install -r requirements-web.txt          # FastAPI + uvicorn

# 3) RAG 依賴（index / search-dense / ask 才需要）
pip install -r requirements-rag.txt          # sentence-transformers/bge-m3、numpy、openai、python-dotenv

# 4) 前端 build（要跑 web 介面才需要，需 Node）
cd web && npm install && npm run build && cd ..

# 5) RAG 生成端設定：複製 .env.example → .env，填 base_url / 金鑰 / 模型
cp .env.example .env
```

### 放原始資料

```
data/
  ├─ <hash>/conversations-*.json             ChatGPT 匯出
  ├─ ttl/30d/…/prod-grok-backend.json        Grok 匯出
  └─ Takeout/…/Gemini Apps_JSON/我的活動.json  Gemini（Google Takeout）
```

Claude Code 不必放進 `data/` —— 直接讀本機 `~/.claude/projects/`（可用 `--claude-path` 或
`CLAUDE_PROJECTS` 覆蓋來源）。

## 常用指令

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

可選全域旗標：`--data <dir>`（預設 `data`）、`--out <dir>`（預設 `out`）。
`ingest` 專屬：`--platforms chatgpt grok`（只處理指定平台）、`--claude-path <dir>`。

### 完整刷新順序（含 Gemini session 還原）

```
ingest   # 產 raw normalized.jsonl（Gemini 為 1問1答 fragment）
stitch   # 用時間 gap 把 Gemini fragment 還原成 session → out/threads.json
ingest   # 重跑：archive.db 在消費端套 threads.json overlay
index    # vectors.db 同樣套 overlay
```

只更新資料（沒改程式）時，重跑 `ingest`（必要時加 `stitch` + `index`）即可，web 唯讀讀同一個 DB。

回歸檢查（Claude parser）：`PYTHONPATH=. python3 scripts/verify_claude_parser.py`。

## Web 介面

搜尋＋讀全文、平台篩選、瀏覽／最近清單、統計儀表板，外加「圖書館長」RAG 問答。

```bash
python -m ai_archive.cli web                       # 預設 http://127.0.0.1:8765
python -m ai_archive.cli web --host 0.0.0.0 --port 2448   # 指定位址／port
```

資料更新後重跑 `ingest` 即生效（web 唯讀讀同一個 DB）。

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

## 隱私

索引／向量化／檢索**全在本地、零外連**；只有 RAG 最終「檢索到的片段」會送生成端。
`data/`、`out/`、`.env`、`PLAN.local.md` 皆 gitignored，GitHub repo 為 public、只推程式碼。
換 RAG 模型／供應商＝改 `.env`，不動程式。
