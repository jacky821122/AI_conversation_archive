"""Parser 共用工具：時間解析、HTML 去標籤。"""

from __future__ import annotations

from datetime import datetime
from html.parser import HTMLParser


def mongo_or_epoch(value) -> float | None:
    """把可能是數字或 Mongo extended-JSON 的時間轉成 epoch 秒。

    支援：
      - int/float（秒）
      - {"$date": {"$numberLong": "<毫秒>"}}
      - {"$date": "<ISO8601>"}
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict) and "$date" in value:
        date = value["$date"]
        if isinstance(date, dict) and "$numberLong" in date:
            return int(date["$numberLong"]) / 1000.0
        if isinstance(date, (int, float)):
            return float(date) / 1000.0
        if isinstance(date, str):
            return iso_to_epoch(date)
    return None


def iso_to_epoch(s: str) -> float | None:
    """ISO8601（含結尾 Z）轉 epoch 秒。"""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


class _TextExtractor(HTMLParser):
    """把 HTML 轉成純文字，區塊級標籤換成換行。"""

    _BLOCK = {
        "p", "br", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
        "ul", "ol", "blockquote", "pre", "hr", "table",
    }

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._BLOCK:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._BLOCK:
            self._parts.append("\n")

    def handle_data(self, data):
        self._parts.append(data)

    def text(self) -> str:
        raw = "".join(self._parts)
        # 收斂多餘空白行
        lines = [ln.strip() for ln in raw.splitlines()]
        out: list[str] = []
        for ln in lines:
            if ln or (out and out[-1]):
                out.append(ln)
        return "\n".join(out).strip()


def html_to_text(html: str) -> str:
    p = _TextExtractor()
    p.feed(html)
    return p.text()
