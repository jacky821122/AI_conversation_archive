"""Parser 共用工具：時間解析、citation 清理、HTML 去標籤。"""

from __future__ import annotations

import re
from datetime import datetime
from html.parser import HTMLParser


def iso_to_epoch(s: str) -> float | None:
    """ISO8601（含結尾 Z）轉 epoch 秒。"""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def mongo_or_epoch(value) -> float | None:
    """把可能是數字、ISO 字串或 Mongo extended-JSON 的時間轉成 epoch 秒。

    支援：
      - int/float（秒）
      - "<ISO8601>"（Grok 的 conv create_time/modify_time 即此格式）
      - {"$date": {"$numberLong": "<毫秒>"}}（Grok 的 response create_time）
      - {"$date": "<ISO8601>"}
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return iso_to_epoch(value)
    if isinstance(value, dict) and "$date" in value:
        date = value["$date"]
        if isinstance(date, dict) and "$numberLong" in date:
            return int(date["$numberLong"]) / 1000.0
        if isinstance(date, (int, float)):
            return float(date) / 1000.0
        if isinstance(date, str):
            return iso_to_epoch(date)
    return None


# ChatGPT 在回應內嵌的 citation/導覽標記：以私有區 unicode U+E200..U+E201
# 包夾（內含 "cite…turn…search…"），渲染時變亂碼方框。整段移除。
_CITE_RE = re.compile(".*?", re.DOTALL)
_PUA_RE = re.compile("[-]")


# Grok 在回應內嵌的 citation：XML 式標籤 <grok:render …>…</grok:render>。
_GROK_RE = re.compile(r"<grok:render\b[^>]*>.*?</grok:render>", re.DOTALL)
_GROK_TAG_RE = re.compile(r"</?grok:[^>]*>")


def clean_text(text: str) -> str:
    """清掉各家 AI 的 citation 噪音與殘留私有區字元。

    - ChatGPT：私有區 U+E200..U+E201 包夾的 cite token
    - Grok：<grok:render …>…</grok:render> 標籤
    """
    if not text:
        return text
    text = _CITE_RE.sub("", text)
    text = _GROK_RE.sub("", text)
    text = _GROK_TAG_RE.sub("", text)  # 後備：清掉殘留的單邊 grok 標籤
    text = _PUA_RE.sub("", text)
    return text


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
