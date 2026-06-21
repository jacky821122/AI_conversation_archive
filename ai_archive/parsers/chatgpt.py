"""ChatGPT (OpenAI 官方匯出) parser。

每個 conversations-*.json 是 list[conv]。每段 conv 的訊息存在 `mapping`
樹裡（因可編輯/重生成而分支）。我們從 `current_node` 沿 `parent` 回溯到
root、反轉，取出使用者實際看到的那條線性對話。

content_type 處理：
  - text            → 取 parts 中的字串
  - multimodal_text → 取字串 parts；非字串 part(資產指標) 記為 attachment
  - thoughts / reasoning_recap → CoT，略過（非使用者語料）
其餘 content_type、以及 user/assistant 以外的 role，一律略過。
"""

from __future__ import annotations

import glob
import json
import os
from typing import Iterator

from ..schema import Conversation, Message

_KEEP_ROLES = {"user", "assistant"}
_KEEP_CONTENT = {"text", "multimodal_text"}


def _linear_node_ids(mapping: dict, current_node: str | None) -> list[str]:
    """從 current_node 回溯到 root，回傳由舊到新的 node id 串。"""
    if not current_node or current_node not in mapping:
        # fallback：找沒有 parent 的 root，往下走 children 的最後一條
        return _fallback_order(mapping)
    chain: list[str] = []
    seen: set[str] = set()
    node = current_node
    while node and node in mapping and node not in seen:
        seen.add(node)
        chain.append(node)
        node = mapping[node].get("parent")
    chain.reverse()
    return chain


def _fallback_order(mapping: dict) -> list[str]:
    roots = [nid for nid, n in mapping.items() if not n.get("parent")]
    if not roots:
        return list(mapping.keys())
    order: list[str] = []
    node = roots[0]
    seen: set[str] = set()
    while node and node not in seen:
        seen.add(node)
        order.append(node)
        children = mapping.get(node, {}).get("children") or []
        node = children[-1] if children else None
    return order


def _message_text(content: dict) -> tuple[str, list[str]]:
    parts = content.get("parts") or []
    texts: list[str] = []
    attachments: list[str] = []
    for p in parts:
        if isinstance(p, str):
            if p.strip():
                texts.append(p)
        elif isinstance(p, dict):
            ptr = p.get("asset_pointer") or p.get("content_type") or "attachment"
            attachments.append(str(ptr))
    return "\n".join(texts).strip(), attachments


def _convert(conv: dict) -> Conversation | None:
    mapping = conv.get("mapping") or {}
    messages: list[Message] = []
    for nid in _linear_node_ids(mapping, conv.get("current_node")):
        msg = mapping[nid].get("message")
        if not msg:
            continue
        role = (msg.get("author") or {}).get("role")
        if role not in _KEEP_ROLES:
            continue
        content = msg.get("content") or {}
        if content.get("content_type") not in _KEEP_CONTENT:
            continue
        text, attachments = _message_text(content)
        if not text and not attachments:
            continue
        messages.append(Message(role=role, text=text,
                                time=msg.get("create_time"),
                                attachments=attachments))
    if not messages:
        return None
    cid = conv.get("conversation_id") or conv.get("id")
    return Conversation(
        id=f"chatgpt:{cid}",
        platform="chatgpt",
        title=conv.get("title") or "",
        create_time=conv.get("create_time"),
        update_time=conv.get("update_time"),
        messages=messages,
    )


def discover(data_dir: str) -> list[str]:
    return sorted(glob.glob(os.path.join(data_dir, "**", "conversations-*.json"),
                            recursive=True))


def parse(data_dir: str) -> Iterator[Conversation]:
    for path in discover(data_dir):
        with open(path, encoding="utf-8") as f:
            for conv in json.load(f):
                c = _convert(conv)
                if c is not None:
                    yield c
