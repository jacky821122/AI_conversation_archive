# 架構與設計

本檔記錄「專案長怎樣、為什麼這樣做」——程式結構、資料流、與不易從 code 直接看出的設計原理。
使用方式（建置／指令）見 `README.md`；協作準則見 `CLAUDE.md`；本機開發路線與個人脈絡見
`PLAN.local.md`（不進 git）。

## 目標

把 ChatGPT / Grok / Gemini / Claude Code 的對話匯出統一成一份個人語料庫，做成可搜尋、
可問答的第二大腦。兩大目標：

1. **RAG 第二大腦** — 用自然語言問「我之前對 X 的想法」，本地檢索 → 生成端作答附出處。
2. **persona 萃取** — 從海量對話提煉個人語氣／個性／思考模式（規劃中）。

## 隱私邊界（最高原則）

索引／向量化／檢索**全在本地、零外連**；只有 RAG 最終「檢索到的片段」會送生成端。
`data/`、`out/`、`.env`、`PLAN.local.md` 皆 gitignored，GitHub repo 為 **public，只推程式碼**。

## 程式結構

```
ai_archive/
  schema.py          統一 Conversation / Message dataclass + JSONL 讀寫
  parsers/
    __init__.py      registry: platform -> parse_fn（新增平台只動這）
    _util.py         時間解析、內嵌標註清理/解包、HTML 去標籤
    chatgpt.py       mapping 樹線性化
    grok.py          responses → 正規化
    gemini.py        My Activity JSON → 迷你兩則對話 fragment
    claude.py        ~/.claude/projects/*.jsonl → session 對話（prose only）
  store.py           SQLite schema + FTS5(trigram) + search/get_conversation/...
  embed.py           bge-m3 本地向量化 + 對話分塊（強制 HF_HUB_OFFLINE）
  index.py           建 out/vectors.db（float32 BLOB + 選配 sqlite-vec）+ dense 檢索
  rag.py             混合檢索（dense+FTS, RRF）→ 生成端作答附出處
  stitch.py          Gemini session 還原（時間 gap 切 session）
  api.py             FastAPI：/api/* 端點 + serve 前端 dist
  cli.py             ingest / list / get / search / stats / index / search-dense / ask / stitch / web
web/                 Vite + React + TS 前端（dist 為 build 產物，不進 git）
deploy/              systemd 服務（port 2448）
```

### 新增平台

只在 `ai_archive/parsers/` 加一個模組並在 `__init__.py` 的 registry 註冊；後端其餘階段
（store / index / rag / web）全部 data-driven、零改動。前端再補 `web/src/lib/api.ts` 的
`Platform` 型別／`PLATFORMS`／`platformMeta`（含一個資料色）即可，各頁面迴圈 `PLATFORMS`
自動跟上。核心原則：**下游一律 data-driven，勿在下游 hardcode 平台**。

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

**冪等**：`ingest` / `index` / `stitch` 重跑覆蓋輸出、結果一致。

## 統一 schema（`out/normalized.jsonl`）

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

## 唯讀 read 契約（給 agent / 程式取用）

`list` / `get` 是 `store.list_conversations` / `get_conversation` 的 CLI 薄殼（與
`/api/conversations*` 同源），純 stdlib、零外連、不載模型。`--json` 給程式解析，欄位同
`conversations` 表：`id`／`platform`／`title`／`create_time`／`update_time`／`n_messages`。

```
list --json  → {platform, month, order, limit, offset, total, count, items:[<上述欄位>]}
get  --json  → {<上述欄位>, messages:[{idx, role, text, time}]}   // 依 idx 排序
```

`list` filter：`--platform`／`--month`(YYYY-MM)／`--order`(recent|oldest)／`--limit`／`--offset`。
`id` 即 `<platform>:<原生 id>`，是跨指令的穩定 handle（`list`/`search` 結果 → 餵 `get`）。

## 平台

| 平台 | 來源 | 說明 |
|---|---|---|
| `chatgpt` | `data/**/conversations-*.json` | mapping 樹線性化 |
| `grok` | `data/**/prod-grok-backend.json` | responses → 正規化 |
| `gemini` | `data/**/Gemini Apps_JSON/*.json` | My Activity，1問1答 fragment（見 Gemini session 還原） |
| `claude` | `~/.claude/projects/<cwd>/<sessionId>.jsonl` | 本機 Claude Code session，一檔一對話，prose only |

> **內嵌標註清理（`_util.clean_text`，ChatGPT/Grok 共用）**：ChatGPT 把連結/entity/product 等
> 以私有區 unicode（U+E200..E201 包夾、U+E202 分段）內嵌進文字流，Grok 用 `<grok:render>` 標籤。
> 純導覽/metadata（`cite`、`image_group`、`entity_metadata`…）整段移除；**帶可讀顯示文字者
> （`url`→markdown 連結、`entity` 家族→陣列 `[1]` 顯示名、`video`/`navlist`→標題）解包還原其顯示
> 文字而非整段刪除**——否則會把該顯示的字一起刪掉造成「缺字」。未知型別/解析失敗一律退回刪除。

### Claude Code 紀錄（第四平台）

直接讀本機 `~/.claude/projects/`（一檔 = 一 session），**不需倒進 `data/`**。可用
`ingest --claude-path <dir>` 或 `CLAUDE_PROJECTS` 環境變數覆蓋來源路徑；root 不存在
（例如別台機器）→ 不產出、不報錯。

格式重點（實測）：每行一筆 typed JSON record，只有 `type` 為 `user`/`assistant` 且帶
`message` 者含對話文字；`message.content` 可能是純字串或 block 陣列（block type 有
`text` / `thinking` / `tool_use` / `tool_result`）。**無 session 標題欄位**。

設計決策：

- **prose only**：只留 `text` block（user + assistant），丟掉 `thinking` / `tool_use` /
  `tool_result`。`tool_result` user-record 不帶 text block，故自然消失。與另外三家行為一致，
  對語意檢索／RAG 最乾淨。
- **一 session 一 Conversation**；`id=claude:<sessionId>`，冪等。resume 串接的 session 不合併。
- **drop trivial**：丟掉「沒有任何含文字 user 訊息」的 session（純 tool-run、只有 slash
  command 無輸入的開頭等）。
- **丟掉沒有有用回應的 session**：開頭為 `API Error:` 的 assistant 訊息當噪音濾掉（網路／
  設定壞掉時的回應）；濾掉後若整個 session 無任何 assistant 文字，視為「問了但沒得到有用回應」
  的廢 session 一併丟棄。用 `startswith` 精準命中真 error，不會誤殺內文討論 API error 的真對話。
  網路後來恢復的 session 會保留其正常回應（只丟掉 error 那則）。
- **排除 headless 噪音（可設定）**：headless 用法（排程／cron 餵入大段 agent system prompt、
  warmup／healthcheck ping）會在 `~/.claude/projects` 留下大量雜訊 session，且重要輸出多在別處。
  `CLAUDE_EXCLUDE_PROMPTS`（逗號分隔的前綴清單，或 `--claude-exclude-prompts` flag）讓「首則 user
  訊息以任一前綴開頭」者於 parse 端整段丟棄（同 drop-trivial 那層，不寫進 raw jsonl）。**判別用內容
  （首則訊息）而非資料夾**——同一專案目錄常混著真人手動開發與自動化 run，按資料夾一刀切會誤殺真對話。
  預設空＝不排除（公開碼行為中性）；個人前綴清單放本機 env／`.zshrc.local`，不寫死進 repo（隱私邊界）。
- **合成輸入照收**：user 文字一律收（含 skill 注入、`<system-reminder>`、slash command 展開）；
  prose-only 已天然濾掉不帶 text block 的 `tool_result`。日後要更精細過濾框架雜訊再擴充。
- **範圍全域**：讀 `~/.claude/projects/` 底下所有專案，形成跨專案的第二大腦。
- registry 契約不變（Approach A）：parser 自己從 env／預設讀 root，CLI 用 flag 設 env，特例侷限
  在唯一需要它的 parser，不汙染 `parse_all` 契約與其他 parser。

回歸檢查：`PYTHONPATH=. python3 scripts/verify_claude_parser.py`（repo 無 pytest，純 stdlib
合成 fixture 自驗 prose-only／drop-trivial／API Error 過濾）。

## 中文檢索（trigram）

SQLite 預設 tokenizer 對連續中文切不開（連「淡江大橋」都比不到），故 FTS5 改用內建
**trigram** tokenizer（連續中文可比對）。trigram 僅支援 ≥3 字查詢，`search` 對 <3 字 query
自動退回 `LIKE` 全表掃描。`search()` 另支援 phrase／or 模式。語意層的中文檢索由本地 bge-m3
embedding 負責。

## Token 估算（時間軸度量）

時間軸除了對話則數，另提供 token 視角的對比。token 在 `ingest` 時用純 stdlib heuristic 估算
（CJK 1 字 ≈ 1 token、其餘 4 字元 ≈ 1 token）存進 `messages.tokens`；`distribution()` 以
per-conversation 子查詢加總，避免膨脹對話計數。刻意不引入 tokenizer 依賴——精準度不重要，跨
平台同一把尺即公平。token 只進 SQLite（DB 衍生資料），不寫回 `normalized.jsonl`。

## Gemini session 還原（stitch）

Gemini 匯出無 thread 資訊、被切成 1問1答 fragment（394 個）。`stitch` 用時間 gap（預設
60 分）把連續坐席還原成 session，產 `out/threads.json`。

關鍵設計——**overlay 在消費端套用，原始資料不被改寫**：

- `normalized.jsonl` 永保 raw fragment（source of truth 不動）。
- `ingest` / `index` 在消費時自動套 overlay：有 `threads.json` 就把 Gemini fragment 合併成
  session。
- 故 archive.db / vectors.db / web / stats 都反映 session（Gemini 394 → 173），但原始
  fragment 永遠可回溯。

完整刷新順序（含 Gemini 還原）：`ingest`（產 raw jsonl）→ `stitch`（產 threads.json）→
`ingest`（archive.db 套 overlay）→ `index`（vectors.db 套 overlay）。

## RAG 問答（ask）

混合檢索：問題經 bge-m3 向量化 → dense top-k；FTS trigram 命中映射回 chunk；兩條 ranked
list 用 **RRF（Reciprocal Rank Fusion）** 融合。檢索全在本地，只有融合後的片段連同問題送
生成端。

- **生成端走 OpenAI 相容介面**，base_url／金鑰／模型皆由 `.env` 設定（見 `.env.example`）——
  換模型／供應商＝改 `.env`，不動程式。
- **模型生命週期**：web 後端把 bge-m3 的 load／release 做成手動端點 + 閒置自動釋放
  （預設 15 分），避免閒置時長佔 VRAM。CUDA context 綁 process 生命週期，要完全歸零需 restart
  service。
- **GPU**：本機有 NVIDIA GPU（WSL），bge-m3 自動走 cuda。

## 依賴分層

- **地基**（ingest / search / stats）：純 stdlib，零安裝。
- **web**：`requirements-web.txt`（FastAPI + uvicorn）。
- **RAG**（index / search-dense / ask）：`requirements-rag.txt`（sentence-transformers／
  bge-m3、numpy、openai、python-dotenv）。

## Web 介面

搜尋＋讀全文、平台篩選、瀏覽／最近清單、統計儀表板，外加「圖書館長」RAG 問答。後端 FastAPI
（唯讀讀 `out/archive.db`、`out/vectors.db`），前端 Vite + React + TS。平台篩選與各平台計數皆
data-driven（`/api/stats` 回什麼前端畫什麼），新增平台前端僅需在 `web/src/lib/api.ts` 補
`PLATFORMS`／`platformMeta`／`Platform` 型別與一個資料色。

### API 端點（皆唯讀）

| 端點 | 說明 |
|---|---|
| `GET /api/stats` | 總數、各平台計數、各月份分佈（每月含對話數 `n` 與 token 估算量 `tokens`） |
| `GET /api/search?q=&platform=&limit=&offset=` | 訊息層級命中 |
| `GET /api/conversations?platform=&order=&limit=&offset=` | 對話清單（瀏覽／最近） |
| `GET /api/conversations/{id}` | 整段對話 |
| `POST /api/ask` | RAG 問答（需 RAG 依賴與 `.env` 生成端設定） |
| `GET /api/model/status` · `POST /api/model/load` · `/api/model/release` | bge-m3 模型生命週期 |
| `GET /api/plan` | 唯讀回本機 `PLAN.local.md`（只供本機 web 檢視；別台無此檔回 `exists:false`） |
