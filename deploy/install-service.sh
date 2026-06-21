#!/usr/bin/env bash
# 安裝 / 更新 ai-archive systemd 系統服務（開機自起、掛了自動重啟）。
# 用法：bash deploy/install-service.sh   （會提示輸入 sudo 密碼）
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT="ai-archive.service"

echo "→ 安裝 $UNIT 到 /etc/systemd/system（需要 sudo 密碼）"
sudo cp "$HERE/$UNIT" "/etc/systemd/system/$UNIT"
sudo systemctl daemon-reload
sudo systemctl enable --now "$UNIT"

echo
echo "→ 服務狀態："
systemctl status "$UNIT" --no-pager -l | head -12
echo
echo "完成。瀏覽器開 http://127.0.0.1:2448（或經 tailscale 從別的裝置開）"
echo "常用：systemctl status/restart/stop ai-archive ；日誌 journalctl -u ai-archive -f"
