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

`requirements-dev.txt` 目前 pin 在 `playwright==1.60.0`。

### 為什麼 pin 了還是可能對不齊：lib 與 browser 是兩條版本線

pin 只鎖得住 Python 套件。**瀏覽器不是 Python 套件、不在 venv 裡**——`playwright install`
會把它下載到 `~/.cache/ms-playwright/` 這個全機共用快取（跨 venv、跨專案，連 npm 版的
playwright 都共用同一個目錄），`pip install -r` 完全不會碰它。

而每個 playwright 版本硬綁一個 chromium build 編號（`1.60.0` → build **1223**）。若快取
裡只有其他工具下載的別的 build，啟動會直接失敗：

```
Executable doesn't exist at ~/.cache/ms-playwright/chromium_headless_shell-1223/...
```

兩條路：補下載對應 build（`playwright install chromium`），或改用快取裡已存在的 build
（見下面的 `PLAYWRIGHT_CHROMIUM`，不必連網）。

### 在有 Zscaler / 企業憑證代理的機器

`playwright install chromium` 會從 CDN 下載 binary，可能撞憑證；`pip` / `uv` 連 pypi 也
可能出現 `invalid peer certificate: UnknownIssuer`（`uv` 需加 `--native-tls` 或
`UV_NATIVE_TLS=1` 才改用系統 CA）。依該機器的憑證設定處理（本專案不替特定機器內建
workaround）；若只是要跑截圖，用下面的 `PLAYWRIGHT_CHROMIUM` 完全不用連網。

### `PLAYWRIGHT_CHROMIUM`：指定現成的瀏覽器，跳過下載

`scripts/shoot.py` 讀這個環境變數；設了就用它，跳過 playwright 自帶下載與 OS 檢查。
三種用得上的情況：

**1. 快取裡有別的 build（build 編號對不上）**

```bash
ls ~/.cache/ms-playwright/          # 看有哪些 build
PLAYWRIGHT_CHROMIUM=$HOME/.cache/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell \
    python scripts/shoot.py
```

差幾個 build 通常照跑；真的開不起來再換另一顆試。

**2. 下載被憑證代理擋住** —— 同上，完全不用連網。

**3. playwright 尚未支援的新版 OS**

若 `playwright install chromium` 報 `does not support chromium on <os>`（OS 比 playwright
的對照表新），改用系統瀏覽器：

```bash
sudo snap install chromium           # Ubuntu：snap 或 apt
which chromium                       # 例 /snap/bin/chromium
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
python scripts/shoot.py --conv 'claude:xxxx'       # 對話頁指定某段（預設取最近一段）
```

> 驗證本機改動時，`--base-url` 不要指向 systemd 常駐的那份：它服務的是自己那份
> `web/dist`，不是你剛 build 出來的，截出來會是舊版面。

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
