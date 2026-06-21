"""Grok (xAI 後端匯出) parser。

prod-grok-backend.json → {"conversations": [...], ...}
每項 = {"conversation": {...}, "responses": [{"response": {...}}, ...]}
response 內含 message / sender(human|ASSISTANT) / create_time(Mongo $date)。
其餘 projects / tasks / media_posts 與 prod-mc-*.json 一律忽略。
"""

from __future__ import annotations

import glob
import json
import os
from typing import Iterator

from ..schema import Conversation, Message
from ._util import mongo_or_epoch


def _convert(item: dict) -> Conversation | None:
    conv = item.get("conversation") or {}
    responses = item.get("responses") or []
    rows: list[tuple[float | None, Message]] = []
    for r in responses:
        rr = r.get("response") or {}
        text = (rr.get("message") or "").strip()
        if not text:
            continue
        role = "user" if rr.get("sender") == "human" else "assistant"
        t = mongo_or_epoch(rr.get("create_time"))
        rows.append((t, Message(role=role, text=text, time=t)))
    if not rows:
        return None
    # 依時間排序（None 視為 0，維持原序）
    rows.sort(key=lambda x: (x[0] is None, x[0] or 0))
    messages = [m for _, m in rows]
    return Conversation(
        id=f"grok:{conv.get('id')}",
        platform="grok",
        title=conv.get("title") or "",
        create_time=mongo_or_epoch(conv.get("create_time")),
        update_time=mongo_or_epoch(conv.get("modify_time")),
        messages=messages,
    )


def discover(data_dir: str) -> list[str]:
    return sorted(glob.glob(os.path.join(data_dir, "**", "prod-grok-backend.json"),
                            recursive=True))


def parse(data_dir: str) -> Iterator[Conversation]:
    for path in discover(data_dir):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for item in data.get("conversations") or []:
            c = _convert(item)
            if c is not None:
                yield c
