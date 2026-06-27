"""Parser 共用工具：時間解析、內嵌標註清理/解包、HTML 去標籤。"""

from __future__ import annotations

import json
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


# ChatGPT 在回應內嵌的標註 token：以私有區 unicode U+E200..U+E201 包夾，內部再用
# U+E202 分段，格式為  <type><payload…> 。這些字元無字形、渲染成亂碼方框。
# 處理分兩類：純導覽/metadata（cite/image_group…）整段移除；帶可讀顯示文字者
# （url/entity 家族…）解包還原顯示文字，避免把該顯示的字一起刪掉造成「缺字」。
_INLINE_TOKEN_RE = re.compile("(.*?)", re.DOTALL)
_PUA_RE = re.compile("[-]")  # 後備：掃掉任何殘留私有區字元
_E202 = ""

# 顯示文字在「第 1 段純文字」的型別（url 的第 2 段是網址）。
_TEXT_SEG_TYPES = {"url", "video", "navlist"}
# 顯示文字在「JSON 陣列 [1]」的 entity 家族。entity_metadata 不在此列——它的 [1]
# 是版面提示（如 "one-line"）而非名稱，故歸入移除。
_ARRAY_ENTITY_TYPES = {
    "entity", "brand", "medication", "scientific_concept",
    "product", "product_entity",
}


def _unwrap_token(body: str) -> str:
    """把 U+E200..E201 內的 token body 還原成可讀文字；無顯示文字者回空字串。

    body 形如 "<type><seg1><seg2>…"。未知型別／解析失敗一律回 ""
    （維持「當噪音刪除」的安全行為，絕不留 PUA 或 raw payload 殘渣）。
    """
    segs = body.split(_E202)
    typ = segs[0]
    if typ in _TEXT_SEG_TYPES and len(segs) >= 2 and segs[1].strip():
        disp = segs[1].strip()
        if typ == "url" and len(segs) >= 3 and segs[2].strip().startswith("http"):
            return f"[{disp}]({segs[2].strip()})"
        return disp
    if typ in _ARRAY_ENTITY_TYPES and len(segs) >= 2:
        try:
            arr = json.loads(segs[1])
        except (ValueError, TypeError):
            arr = None
        if (isinstance(arr, list) and len(arr) >= 2
                and isinstance(arr[1], str) and arr[1].strip()):
            return arr[1].strip()
    return ""


# Grok 在回應內嵌的 citation：XML 式標籤 <grok:render …>…</grok:render>。
_GROK_RE = re.compile(r"<grok:render\b[^>]*>.*?</grok:render>", re.DOTALL)
_GROK_TAG_RE = re.compile(r"</?grok:[^>]*>")


def clean_text(text: str) -> str:
    """清掉各家 AI 的內嵌標註噪音與殘留私有區字元。

    - ChatGPT：U+E200..E201 包夾的 token——純 metadata 移除，帶顯示文字者解包還原。
    - Grok：<grok:render …>…</grok:render> 標籤。
    """
    if not text:
        return text
    text = _INLINE_TOKEN_RE.sub(lambda m: _unwrap_token(m.group(1)), text)
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
