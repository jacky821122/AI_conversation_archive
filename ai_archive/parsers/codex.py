"""Codex 本機 rollout parser：一個 session 一段 prose-only 對話。

預設讀 $CODEX_HOME（或 ~/.codex）的 sessions 與 archived_sessions；
CODEX_SESSIONS 可覆蓋為單一來源根目錄，不讀 data_dir。
user 優先取 UI 事件，assistant 優先取 response_item，避免雙份紀錄與框架注入。
沒有 UI user 事件或 response assistant 的舊紀錄，分別退回另一種來源。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterator

from ..schema import Conversation, Message
from ._util import iso_to_epoch

_UI_NOISE_PREFIXES = (
    "# AGENTS.md instructions",
    "<environment_context>",
    "<task-notification>",
    "<local-command-caveat>",
    "<local-command-stdout>",
    "<command-name>",
    "<command-message>",
    "<command-args>",
    "<system-reminder>",
    "<turn_aborted>",
    "<codex_internal_context",
    "<skill>",
)


def _text(content, role: str) -> str:
    if isinstance(content, str):
        parts = [content]
    elif isinstance(content, list):
        parts = [
            part["text"] for part in content
            if isinstance(part, dict)
            and part.get("type") in ("text", "input_text", "output_text")
            and isinstance(part.get("text"), str)
        ]
    else:
        return ""
    text = "\n".join(
        part.strip() for part in parts
        if part.strip() and not (
            role == "user" and part.lstrip().startswith(_UI_NOISE_PREFIXES)
        )
    ).strip()
    if role == "user" and text.startswith("<send_user_message_question_reply>"):
        raw = text.removeprefix("<send_user_message_question_reply>").removesuffix(
            "</send_user_message_question_reply>"
        ).strip()
        try:
            replies = json.loads(raw)
        except json.JSONDecodeError:
            return ""
        if not isinstance(replies, list):
            return ""
        return "\n".join(reply["answer"].strip() for reply in replies
                         if isinstance(reply, dict) and isinstance(reply.get("answer"), str)).strip()
    return text


def _parse_file(path: str) -> Conversation | None:
    session_id = None
    responses: dict[str, list[tuple[int, Message]]] = {"user": [], "assistant": []}
    events: dict[str, list[tuple[int, Message]]] = {"user": [], "assistant": []}
    replies: list[tuple[int, Message]] = []
    with open(path, encoding="utf-8") as stream:
        for position, line in enumerate(stream):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict):
                continue
            record_type = record.get("type")
            if record_type == "session_meta":
                source = payload.get("source")
                if source == "subagent" or (
                    isinstance(source, dict) and "subagent" in source
                ):
                    return None
                session_id = payload.get("id") or payload.get("session_id")
                continue
            if record_type == "response_item" and payload.get("type") == "message":
                role = payload.get("role")
                content = payload.get("content")
                target = responses
            elif record_type == "event_msg":
                kind = payload.get("type")
                if kind in ("user_message", "agent_message"):
                    role = "user" if kind == "user_message" else "assistant"
                    content = payload.get("message")
                elif kind == "item_completed":
                    payload = payload.get("item")
                    if not isinstance(payload, dict):
                        continue
                    if payload.get("type") not in ("UserMessage", "AgentMessage"):
                        continue
                    role = "user" if payload["type"] == "UserMessage" else "assistant"
                    content = payload.get("content")
                else:
                    continue
                target = events
            else:
                continue
            if not isinstance(role, str) or role not in target or payload.get("channel") == "analysis":
                continue
            text = _text(content, role)
            if text:
                timestamp = record.get("timestamp")
                entry = (position, Message(
                    role=role, text=text,
                    time=iso_to_epoch(timestamp) if isinstance(timestamp, str) else None,
                ))
                target[role].append(entry)
                if record_type == "response_item" and role == "user" and any(
                    isinstance(part, dict) and isinstance(part.get("text"), str)
                    and part["text"].lstrip().startswith("<send_user_message_question_reply>")
                    for part in (content if isinstance(content, list) else [{"text": content}])
                ):
                    replies.append(entry)

    users = events["user"] or responses["user"]
    if events["user"]:
        users = sorted(users + replies)
    assistants = responses["assistant"] or events["assistant"]
    if not isinstance(session_id, str) or not session_id or not users or not assistants:
        return None
    prefixes = tuple(
        prefix.strip() for prefix in os.environ.get("CODEX_EXCLUDE_PROMPTS", "").split(",")
        if prefix.strip()
    )
    if prefixes and users[0][1].text.startswith(prefixes):
        return None
    messages = [message for _, message in sorted(users + assistants)]
    times = [message.time for message in messages if message.time is not None]
    return Conversation(
        id=f"codex:{session_id}", platform="codex",
        title=users[0][1].text.replace("\n", " ")[:60],
        create_time=min(times) if times else None,
        update_time=max(times) if times else None,
        messages=messages,
    )


def discover(data_dir: str) -> list[str]:
    override = os.environ.get("CODEX_SESSIONS")
    home = Path(os.path.expanduser(os.environ.get("CODEX_HOME") or "~/.codex"))
    roots = [Path(os.path.expanduser(override))] if override else [
        home / "sessions", home / "archived_sessions",
    ]
    return sorted(str(path) for root in roots for path in root.rglob("rollout-*.jsonl")
                  if path.is_file())


def parse(data_dir: str) -> Iterator[Conversation]:
    for path in discover(data_dir):
        conversation = _parse_file(path)
        if conversation is not None:
            yield conversation
