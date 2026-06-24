# AI Conversation Archive — AI 協作準則

把個人的 ChatGPT / Grok / Gemini / Claude Code 對話匯出，做成可搜尋、可問答的語料庫與第二大腦。

## ⚠️ 開工前先讀進度檔

**專案的計畫、進度、決策脈絡在 `PLAN.local.md`（gitignored，本機才有）。每個 session 開始處理
本專案前，先讀 `PLAN.local.md`** — 它是 source of truth，記錄「為什麼這樣做、接下來的路線、踩過
的坑」與個人脈絡，git log 只記「改了什麼」。若該檔不存在（例如別台機器 clone），以 git log +
`ARCHITECTURE.md` 接續，並提醒使用者。

## 文件分工（改文件時對號入座）

- **`README.md`** — 純使用手冊（環境建置、指令、跑法）。手冊資訊置頂、一眼可見；不放設計原理。
- **`ARCHITECTURE.md`** — 不敏感的架構與設計原理（程式結構、資料流、schema、各設計「為什麼」）。進 git。
- **`PLAN.local.md`** — 本機 SoT，含個人記憶／可能敏感內容、預計開發、決策歷史。**不進 git**。
- **`CLAUDE.md`**（本檔）— 協作準則與不易從 code 看出的慣例摘要。

> 架構樹、資料流、各平台與設計原理的細節都在 `ARCHITECTURE.md`；指令與建置在 `README.md`。
> 本檔只留「協作時要記得的準則」，不重複那些內容。

## 慣例與邊界（不易從 code 直接看出的）

- **隱私邊界（最高原則）**：索引／向量化／檢索全在本地、零外連；只有 RAG 最終「檢索到的片段」
  會送生成端。`data/`、`out/`、`.env`、`PLAN.local.md` 皆 gitignored。GitHub repo 為
  **public，只推程式碼**。改任何東西前先確認不會把私人資料或敏感脈絡推上 public repo。
- **依賴分層**：地基純 stdlib（ingest/search/stats，零安裝）；web 用 `requirements-web.txt`；
  RAG 用 `requirements-rag.txt`。動地基層時不要引入第三方依賴。
- **生成端可換**：RAG 走 OpenAI 相容介面，設定全在 `.env`。換模型／供應商＝改 `.env`，不動程式。
- **新增平台**：只在 `ai_archive/parsers/` 加模組並在 `__init__.py` 註冊；下游（store/index/
  rag/web）全 data-driven，勿在下游 hardcode 平台。web 前端新增平台補 `web/src/lib/api.ts` 的
  `Platform`／`PLATFORMS`／`platformMeta` 即可，各頁面迴圈 PLATFORMS 自動跟上。
- **Gemini overlay 在消費端**：`normalized.jsonl` 永保 raw fragment（不改寫）；`ingest`/`index`
  消費時才套 `threads.json` overlay。不要把 overlay 寫回原始檔。
- **冪等**：`ingest` / `index` / `stitch` 重跑須覆蓋輸出、結果一致。改這些指令時維持冪等。
