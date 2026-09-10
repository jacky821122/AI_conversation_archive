"""Standalone regression check for the Claude Code parser (repo has no pytest).

Builds a synthetic .jsonl in a temp dir, points CLAUDE_PROJECTS at it,
and asserts the parser extracts prose-only messages, drops trivial
sessions, and sets id/title/time correctly.

Run from the repo root:
    PYTHONPATH=. python scripts/verify_claude_parser.py
"""

import json
import os
import tempfile

from ai_archive.parsers import claude


def _write_session(root, slug, session_id, records):
    d = os.path.join(root, slug)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{session_id}.jsonl"), "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main():
    with tempfile.TemporaryDirectory() as root:
        # Session A: real prose + noise blocks that must be dropped.
        _write_session(root, "proj-a", "sess-a", [
            {"type": "user", "sessionId": "sess-a",
             "timestamp": "2026-06-24T08:00:00.000Z",
             "message": {"role": "user", "content": "幫我看這個 bug"}},
            {"type": "assistant", "sessionId": "sess-a",
             "timestamp": "2026-06-24T08:00:05.000Z",
             "message": {"role": "assistant", "content": [
                 {"type": "thinking", "thinking": "internal noise"},
                 {"type": "text", "text": "好的，我來看看"},
                 {"type": "tool_use", "name": "Read", "input": {}},
             ]}},
            {"type": "user", "sessionId": "sess-a",
             "timestamp": "2026-06-24T08:00:09.000Z",
             "message": {"role": "user", "content": [
                 {"type": "tool_result", "content": "huge file dump..."},
             ]}},
            {"type": "system", "sessionId": "sess-a",
             "timestamp": "2026-06-24T08:00:10.000Z", "subtype": "x"},
        ])
        # Session B: trivial — assistant-only, no user text → must be dropped.
        _write_session(root, "proj-b", "sess-b", [
            {"type": "assistant", "sessionId": "sess-b",
             "timestamp": "2026-06-24T09:00:00.000Z",
             "message": {"role": "assistant", "content": [
                 {"type": "tool_use", "name": "Bash", "input": {}},
             ]}},
        ])
        # Session C: user 有文字，但 assistant 只有 API Error → 濾掉後無回應，丟棄。
        _write_session(root, "proj-c", "sess-c", [
            {"type": "user", "sessionId": "sess-c",
             "timestamp": "2026-06-24T10:00:00.000Z",
             "message": {"role": "user", "content": "在嗎"}},
            {"type": "assistant", "sessionId": "sess-c",
             "timestamp": "2026-06-24T10:00:02.000Z",
             "message": {"role": "assistant", "content":
                 "API Error: The socket connection was closed unexpectedly."}},
        ])
        # Session D: 混雜 — 一則 API Error + 一則正常回應 → 保留，error 被濾掉。
        _write_session(root, "proj-d", "sess-d", [
            {"type": "user", "sessionId": "sess-d",
             "timestamp": "2026-06-24T11:00:00.000Z",
             "message": {"role": "user", "content": "重試一下"}},
            {"type": "assistant", "sessionId": "sess-d",
             "timestamp": "2026-06-24T11:00:01.000Z",
             "message": {"role": "assistant", "content":
                 "API Error: 400 something broke"}},
            {"type": "assistant", "sessionId": "sess-d",
             "timestamp": "2026-06-24T11:00:09.000Z",
             "message": {"role": "assistant", "content": "好了，這是答案"}},
        ])

        # Session E: 首則 user 訊息命中排除前綴（headless cron/ping 噪音）→ 丟棄。
        _write_session(root, "proj-e", "sess-e", [
            {"type": "user", "sessionId": "sess-e",
             "timestamp": "2026-06-24T12:00:00.000Z",
             "message": {"role": "user", "content":
                 "# Bot — automated run\nYou are a scheduled agent."}},
            {"type": "assistant", "sessionId": "sess-e",
             "timestamp": "2026-06-24T12:00:03.000Z",
             "message": {"role": "assistant", "content": "done"}},
        ])

        # Session F: queued prompt（真人趁 Claude 忙碌時送出）只存在於
        # attachment 記錄裡，必須收；task-notification 則不收（機器產生）。
        _write_session(root, "proj-f", "sess-f", [
            {"type": "user", "sessionId": "sess-f",
             "timestamp": "2026-06-24T13:00:00.000Z",
             "message": {"role": "user", "content": "先跑起來"}},
            {"type": "assistant", "sessionId": "sess-f",
             "timestamp": "2026-06-24T13:00:02.000Z",
             "message": {"role": "assistant", "content": "開跑了"}},
            {"type": "queue-operation", "operation": "enqueue",
             "timestamp": "2026-06-24T13:00:30.000Z", "content": "順便看一下 log"},
            {"type": "user", "sessionId": "sess-f",
             "timestamp": "2026-06-24T13:01:00.000Z",
             "message": {"role": "user", "content":
                 "<task-notification>\n<task-id>abc</task-id>\n</task-notification>"}},
            {"type": "attachment", "sessionId": "sess-f",
             "timestamp": "2026-06-24T13:01:05.000Z",
             "attachment": {"type": "queued_command", "commandMode": "prompt",
                            "origin": {"kind": "human"},
                            "timestamp": "2026-06-24T13:00:30.000Z",
                            "prompt": "順便看一下 log"}},
            {"type": "attachment", "sessionId": "sess-f",
             "timestamp": "2026-06-24T13:01:06.000Z",
             "attachment": {"type": "queued_command",
                            "commandMode": "task-notification",
                            "timestamp": "2026-06-24T13:01:06.000Z",
                            "prompt": "<task-notification>bg done</task-notification>"}},
            {"type": "assistant", "sessionId": "sess-f",
             "timestamp": "2026-06-24T13:01:10.000Z",
             "message": {"role": "assistant", "content": "log 看完了"}},
            # CLI 操作紀錄：斜線指令、caveat、其 stdout → 全部不算對話。
            {"type": "user", "sessionId": "sess-f",
             "timestamp": "2026-06-24T13:02:00.000Z",
             "message": {"role": "user", "content":
                 "<local-command-caveat>Caveat: ...</local-command-caveat>"}},
            {"type": "user", "sessionId": "sess-f",
             "timestamp": "2026-06-24T13:02:01.000Z",
             "message": {"role": "user", "content":
                 "<command-name>/exit</command-name>\n<command-args></command-args>"}},
            {"type": "user", "sessionId": "sess-f",
             "timestamp": "2026-06-24T13:02:02.000Z",
             "message": {"role": "user", "content":
                 "<local-command-stdout>Bye!</local-command-stdout>"}},
            # 但 `!` 送進來的指令與輸出是對話的一部分 → 必須留。
            {"type": "user", "sessionId": "sess-f",
             "timestamp": "2026-06-24T13:02:03.000Z",
             "message": {"role": "user", "content":
                 "<bash-input>git status</bash-input>"}},
        ])

        os.environ["CLAUDE_PROJECTS"] = root
        os.environ["CLAUDE_EXCLUDE_PROMPTS"] = "# Bot,ping"
        convs = list(claude.parse("ignored-data-dir"))

    by_id = {c.id: c for c in convs}
    # 只剩 A（正常）、D（混雜留下）、F（queued prompt）；B/C 丟棄，E 命中排除前綴丟棄。
    assert set(by_id) == {"claude:sess-a", "claude:sess-d",
                          "claude:sess-f"}, sorted(by_id)
    c = by_id["claude:sess-a"]
    assert c.platform == "claude", c.platform
    assert c.title == "幫我看這個 bug", repr(c.title)
    # prose-only: 2 messages (user str + assistant text block), noise gone.
    assert len(c.messages) == 2, [m.text for m in c.messages]
    assert c.messages[0].role == "user"
    assert c.messages[0].text == "幫我看這個 bug"
    assert c.messages[1].role == "assistant"
    assert c.messages[1].text == "好的，我來看看"
    assert c.messages[0].time is not None and c.messages[0].time > 0
    assert c.create_time == c.messages[0].time
    assert c.update_time == c.messages[1].time
    # Session D：API Error 那則被濾掉，只剩 user + 正常回應。
    d = by_id["claude:sess-d"]
    assert len(d.messages) == 2, [m.text for m in d.messages]
    assert all(not m.text.startswith("API Error:") for m in d.messages)
    assert d.messages[1].text == "好了，這是答案"
    # Session F：queued prompt 補回來、task-notification（兩種形式）都不留。
    fm = by_id["claude:sess-f"].messages
    assert [m.role for m in fm] == \
        ["user", "assistant", "user", "assistant", "user"], \
        [(m.role, m.text) for m in fm]
    assert fm[2].text == "順便看一下 log", repr(fm[2].text)
    # CLI 操作紀錄全清（含兩種形式的 task-notification）；`!` 的 bash-input 留著。
    for tag in ("task-notification", "local-command-caveat",
                "local-command-stdout", "command-name"):
        assert all(tag not in m.text for m in fm), (tag, [m.text for m in fm])
    assert fm[4].text == "<bash-input>git status</bash-input>", repr(fm[4].text)
    # 時間取 attachment 的入列時刻（13:00:30），不是被 dequeue 的時刻。
    assert fm[2].time == fm[1].time + 28, (fm[1].time, fm[2].time)
    print("OK: all assertions passed")


if __name__ == "__main__":
    main()
