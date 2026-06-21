"""統一的對話正規化 schema 與 JSONL 讀寫。

所有 parser 的輸出、以及後續 Phase B/C 的輸入，都統一成這裡的
Conversation / Message。一段對話 = JSONL 的一行。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable, Iterator


@dataclass
class Message:
    role: str  # "user" | "assistant"
    text: str
    time: float | None = None  # epoch 秒
    attachments: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict = {"role": self.role, "text": self.text}
        if self.time is not None:
            d["time"] = self.time
        if self.attachments:
            d["attachments"] = self.attachments
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        return cls(
            role=d["role"],
            text=d.get("text", ""),
            time=d.get("time"),
            attachments=d.get("attachments", []),
        )


@dataclass
class Conversation:
    id: str  # 例: "chatgpt:<uuid>" / "grok:<uuid>" / "gemini:<hash>"
    platform: str  # "chatgpt" | "grok" | "gemini"
    title: str
    create_time: float | None
    update_time: float | None
    messages: list[Message] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "platform": self.platform,
            "title": self.title,
            "create_time": self.create_time,
            "update_time": self.update_time,
            "messages": [m.to_dict() for m in self.messages],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Conversation":
        return cls(
            id=d["id"],
            platform=d["platform"],
            title=d.get("title", ""),
            create_time=d.get("create_time"),
            update_time=d.get("update_time"),
            messages=[Message.from_dict(m) for m in d.get("messages", [])],
        )


def write_jsonl(convs: Iterable[Conversation], path: str) -> int:
    """寫出 normalized.jsonl，回傳寫出的對話數。"""
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        for c in convs:
            f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
            n += 1
    return n


def read_jsonl(path: str) -> Iterator[Conversation]:
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield Conversation.from_dict(json.loads(line))
