# 視覺測試（headless 截圖）

開發 web UI 時，用 headless Chromium 對跑著的介面截圖，驗證實際渲染、RWD（手機/桌面）、
sticky 標題、互動結果等。**不需要 GUI / X server**——Chromium 離屏渲染直接輸出 PNG，
在純命令列（含 WSL、CI、遠端機）都能跑。

截圖也是給 AI 協作者「看見」畫面的方式：跑完讀 `out/shots/*.png` 即可檢視。

> 隱私：截圖含**真實對話**內容，`out/` 已 gitignore，**絕不可進 public repo**。

## 安裝（一次性）

```bash
pip install -r requirements-dev.txt
playwright install chromium          # 下載自帶 Chromium（約 150MB）
```

Linux（含 WSL）另需系統函式庫：

```bash
playwright install-deps chromium     # 需 sudo；裝 libnss3、libatk… 等
```

macOS / Windows 不需要 `install-deps`。

第一次裝成功後，建議把實際可用的 playwright 版本 pin 回 `requirements-dev.txt`
（例 `playwright==1.49.0`），確保跨機器一致。

### 在有 Zscaler / 企業憑證代理的機器

`playwright install chromium` 會從 CDN 下載 binary，可能撞憑證。若卡住，依該機器的
憑證設定處理（本專案不替特定機器內建 workaround）。

### playwright 尚未支援的新版 OS（用系統 chromium 繞道）

若 `playwright install chromium` 報 `does not support chromium on <os>`（OS 比 playwright
的對照表新），改用系統瀏覽器：

```bash
# Ubuntu：用 snap（或 apt）裝 chromium
sudo snap install chromium
which chromium                       # 例 /snap/bin/chromium
```

再用環境變數指定，`scripts/shoot.py` 會改用它、跳過 playwright 自帶下載與 OS 檢查：

```bash
PLAYWRIGHT_CHROMIUM=/snap/bin/chromium python scripts/shoot.py
```

等 playwright 之後支援該 OS，移除環境變數、改回 `playwright install chromium` 即可。

## 用法

先啟動 web（另一個終端）：

```bash
python -m ai_archive.cli web         # 開發預設 http://127.0.0.1:8765
```

再截圖：

```bash
python scripts/shoot.py                            # 手機+桌面都跑
python scripts/shoot.py --only mobile              # 只手機
python scripts/shoot.py --base-url http://127.0.0.1:2448   # 打 systemd 常駐埠
```

輸出在 `out/shots/`：

| 檔名 | 內容 |
|------|------|
| `desktop-home.png` | 桌面首頁全頁 |
| `desktop-home-tokens.png` | 桌面：時間軸切到 token 後 |
| `mobile-home.png` | 手機首頁（視窗內，看底部分頁列） |
| `mobile-home-full.png` | 手機首頁全頁（看時間軸清單全貌） |
| `mobile-scrolled.png` | 手機捲動後（驗 sticky 標題凍結） |
| `mobile-plan.png` | 手機「計畫」tab |

要驗其他情境（點某年份摺疊、切特定 tab…）就照 `scripts/shoot.py` 的既有情境加一段。
