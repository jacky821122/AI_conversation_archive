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
  store.py           SQLite schema + FTS5(trigram) + search()
  cli.py             ingest / search / stats
```

## 接下來（尚未做）

- **Phase B**：本地 bge-m3 embedding 向量索引 + Claude 作答（`ask`）。
- **Phase C**：抽 user 訊息 → Claude 蒸餾 persona（`persona`）。
- 兩者皆需 `pip install`（sentence-transformers / anthropic 等）與 `ANTHROPIC_API_KEY`。
- 新平台/新匯出：在 `parsers/` 加一個模組並註冊，重跑 `ingest` 即可。
