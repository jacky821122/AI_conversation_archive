"""開發輔助：用 headless Chromium 對跑著的 web 介面截圖（含手機/桌面、互動、捲動）。

不需要 GUI / X server——Playwright 的 Chromium 是離屏渲染，直接輸出 PNG。
給 AI 協作者「看見」版面用：跑完後讀 out/shots/*.png 即可檢視 RWD、sticky、摺疊等。

前置（見 docs/dev-visual-testing.md）：
    pip install -r requirements-dev.txt
    playwright install chromium
    # Linux 另需： playwright install-deps chromium  (需 sudo)

用法（先確保 web 已啟動，例如 `python -m ai_archive.cli web`）：
    python scripts/shoot.py                       # 預設打 http://127.0.0.1:8765
    python scripts/shoot.py --base-url http://127.0.0.1:2448
    python scripts/shoot.py --only mobile         # 只跑手機情境

輸出： out/shots/<scenario>.png （out/ 已 gitignore——截圖含真實對話，絕不上 public repo）。
"""

from __future__ import annotations

import argparse
import os
import sys

# iPhone 13/14 邏輯解析度（直式）；桌面用一般寬螢幕。
MOBILE = {"width": 390, "height": 844}
DESKTOP = {"width": 1280, "height": 900}

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(_ROOT, "out", "shots")


def _save_path(name: str) -> str:
    return os.path.join(OUT_DIR, f"{name}.png")


def run(base_url: str, only: str | None) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit(
            "需要 dev 依賴：pip install -r requirements-dev.txt && "
            "playwright install chromium"
        )

    os.makedirs(OUT_DIR, exist_ok=True)
    saved: list[str] = []

    # 若設了 PLAYWRIGHT_CHROMIUM，用系統瀏覽器（繞過 playwright 自帶下載與 OS 檢查；
    # 例：playwright 尚未支援某新版 OS 時，指向 snap/apt 裝的 chromium）。
    exe = os.environ.get("PLAYWRIGHT_CHROMIUM") or None

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe)  # headless 預設 True

        # ---- 桌面情境 ----
        if only in (None, "desktop"):
            page = browser.new_page(viewport=DESKTOP)
            page.goto(base_url, wait_until="networkidle")
            page.screenshot(path=_save_path("desktop-home"), full_page=True)
            saved.append("desktop-home")

            # 時間軸切到 token（點撥桿開關）後再截一次
            toggle = page.get_by_role("switch")
            if toggle.count():
                toggle.first.click()
                page.wait_for_timeout(300)
                page.screenshot(path=_save_path("desktop-home-tokens"), full_page=True)
                saved.append("desktop-home-tokens")
            page.close()

        # ---- 手機情境 ----
        if only in (None, "mobile"):
            page = browser.new_page(viewport=MOBILE, is_mobile=True,
                                    has_touch=True, device_scale_factor=2)
            page.goto(base_url, wait_until="networkidle")
            # 視窗內截圖（看底部分頁列是否固定、不遮內容）
            page.screenshot(path=_save_path("mobile-home"))
            saved.append("mobile-home")
            # 整頁截圖（看時間軸清單全貌）
            page.screenshot(path=_save_path("mobile-home-full"), full_page=True)
            saved.append("mobile-home-full")

            # 捲動後截圖：驗證時間軸 sticky 標題凍結 + 底部列仍在。
            # 捲到「思緒的時間軸」標題貼齊頂部後再多捲一點，讓月份清單滑進它下方，
            # 才看得出標題凍結（而非整段一起捲走）。
            page.evaluate(
                """() => {
                    const h = [...document.querySelectorAll('h2')]
                        .find(e => e.textContent.includes('思緒的時間軸'));
                    if (h) {
                        const top = h.getBoundingClientRect().top + window.scrollY;
                        window.scrollTo(0, top + 30);
                    }
                }"""
            )
            page.wait_for_timeout(300)
            page.screenshot(path=_save_path("mobile-scrolled"))
            saved.append("mobile-scrolled")

            # 年份摺疊：點「2026」標題收合後截圖（驗證可收合；預設展開）。
            page.evaluate("window.scrollTo(0, 0)")
            year = page.get_by_role("button", name="2026")
            if year.count():
                year.first.click()
                page.wait_for_timeout(300)
                page.screenshot(path=_save_path("mobile-year-collapsed"))
                saved.append("mobile-year-collapsed")

            # 計畫 tab（底部分頁列導覽）
            page.goto(base_url.rstrip("/") + "/plan", wait_until="networkidle")
            page.screenshot(path=_save_path("mobile-plan"))
            saved.append("mobile-plan")
            page.close()

        browser.close()

    print("已輸出：")
    for name in saved:
        print(f"  {_save_path(name)}")


def main() -> None:
    ap = argparse.ArgumentParser(description="對跑著的 web 介面截圖（headless）")
    ap.add_argument("--base-url", default="http://127.0.0.1:8765",
                    help="web 介面位址（預設開發用 8765；systemd 常駐為 2448）")
    ap.add_argument("--only", choices=["mobile", "desktop"],
                    help="只跑某一種版型（預設兩種都跑）")
    args = ap.parse_args()
    run(args.base_url, args.only)


if __name__ == "__main__":
    main()
