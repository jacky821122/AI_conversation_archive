# AI Conversation Archive — AI 協作準則

把個人的 ChatGPT / Grok / Gemini / Claude Code 對話匯出，做成可搜尋、可問答的語料庫與第二大腦。

## 脈絡檔的定位與權威順序

**權威順序（高 → 低）**：當下對話的明示決策　>　`CLAUDE.md`（硬規範）　>
`PLAN.local.md` / `ARCHITECTURE.md`（歷史百科）。

- **唯一的硬規範是本檔（CLAUDE.md）**：要當準則遵守的只有這裡。
- **`PLAN.local.md` / `ARCHITECTURE.md` 是歷史百科，不是聖經**：它們記的是「上次寫下時的真相」。
  使用者常是 implement 一串後才回頭更新文檔，故這兩份**可能落後於 code 與當下對話**。把它們當
  參考、可質疑；與 code 或當下對話衝突時，**以現況為準，並提醒使用者該文檔可能過時**。不要因為
  「文檔沒寫」就斷定某事不存在，也不要拿其中的舊決策推翻對話中剛確立的新決策。
- **按需讀，不是每次硬讀**（PLAN 會越來越肥，瑣碎任務硬讀只是塞雜訊、燒 token）：
  - 需要專案脈絡／決策史（討論方向、設計、實作非瑣碎功能） → 查 `PLAN.local.md`。
  - 需要架構原理（動到資料流、schema、跨模組設計） → 查 `ARCHITECTURE.md`。
  - 瑣碎／局部任務（改變數名、修錯字、單檔小編輯、純問答） → 兩份都不必讀。
  - 要更新某份檔 → 當然先讀那份。
- `PLAN.local.md` 不存在時（別台 clone）→ 以 git log + `ARCHITECTURE.md` 接續，並提醒使用者。

## 文件分工（改文件時對號入座）

- **`README.md`** — 純使用手冊（環境建置、指令、跑法）。手冊資訊置頂、一眼可見；不放設計原理。
- **`ARCHITECTURE.md`** — 不敏感的架構與設計原理（程式結構、資料流、schema、各設計「為什麼」）。進 git。
- **`PLAN.local.md`** — 本機開發計畫，含個人記憶／可能敏感內容、預計開發、決策歷史。**不進 git**。
- **`CLAUDE.md`**（本檔）— 協作準則與不易從 code 看出的慣例摘要。

> 架構樹、資料流、各平台與設計原理的細節都在 `ARCHITECTURE.md`；指令與建置在 `README.md`。
> 本檔只留「協作時要記得的準則」，不重複那些內容。

## 慣例與邊界（不易從 code 直接看出的）

- **隱私邊界（最高原則）**：索引／向量化／檢索全在本地、零外連；只有 RAG 最終「檢索到的片段」
  會送生成端。`data/`、`out/`、`.env`、`PLAN.local.md` 皆 gitignored。GitHub repo 為
  **public，只推程式碼**。改任何東西前先確認不會把私人資料或敏感脈絡推上 public repo。
- **依賴分層**：地基純 stdlib（ingest/search/stats，零安裝）；web 用 `requirements-web.txt`；
  RAG 用 `requirements-rag.txt`。動地基層時基本上不要引入第三方依賴，真的需要就詢問使用者。
- **生成端可換**：RAG 走 OpenAI 相容介面，設定全在 `.env`。換模型／供應商＝改 `.env`，不動程式。
- **新增平台＝下游 data-driven**：勿在下游（store/index/rag/web）hardcode 平台。實際步驟見
  `ARCHITECTURE.md`「新增平台」。
- **Web UI 響應式（RWD）**：任何 Web UI 改動都要同時考慮手機版（以 iOS 為主）與桌面版的呈現與
  操作體驗，兩者皆需驗證，勿只顧其中一種版型。
- **Gemini overlay 在消費端**：`normalized.jsonl` 永保 raw fragment（不改寫）；`ingest`/`index`
  消費時才套 `threads.json` overlay。不要把 overlay 寫回原始檔。
- **冪等**：`ingest` / `index` / `stitch` 重跑須覆蓋輸出、結果一致。改這些指令時維持冪等。
