"""Gemini (Google Takeout「我的活動」JSON) parser。

我的活動.json 是 list，每筆 = 一次 prompt+回應的活動條目：
  - title: "Prompted <完整使用者 prompt>"（實測未截斷）
  - safeHtmlItem[].html: Gemini 的回應（HTML，需去標籤）
  - time: ISO8601
無 conversation id / 無 threading → 每筆解析成「user + assistant」兩則訊息
的迷你對話。id 用內容雜湊以確保重跑穩定。
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
from typing import Iterator

from ..schema import Conversation, Message
from ._util import html_to_text, iso_to_epoch

_PROMPT_PREFIX = "Prompted "


def _convert(item: dict) -> Conversation | None:
    title = item.get("title") or ""
    if not title.startswith(_PROMPT_PREFIX):
        return None  # 只處理 prompt 活動
    user_text = title[len(_PROMPT_PREFIX):].strip()
    if not user_text:
        return None

    html = "\n".join(h.get("html", "") for h in (item.get("safeHtmlItem") or []))
    assistant_text = html_to_text(html)

    t = iso_to_epoch(item.get("time", ""))
    messages = [Message(role="user", text=user_text, time=t)]
    if assistant_text:
        messages.append(Message(role="assistant", text=assistant_text, time=t))

    digest = hashlib.sha1(
        f"{item.get('time','')}\n{user_text}".encode("utf-8")
    ).hexdigest()[:12]
    short = user_text.replace("\n", " ")
    return Conversation(
        id=f"gemini:{digest}",
        platform="gemini",
        title=short[:60],
        create_time=t,
        update_time=t,
        messages=messages,
    )


def discover(data_dir: str) -> list[str]:
    # Takeout 把 Gemini 活動放在 "Gemini Apps_JSON/我的活動.json"
    hits = glob.glob(os.path.join(data_dir, "**", "Gemini Apps_JSON", "*.json"),
                     recursive=True)
    return sorted(hits)


def parse(data_dir: str) -> Iterator[Conversation]:
    for path in discover(data_dir):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            c = _convert(item)
            if c is not None:
                yield c
