"""Standalone sanity check for the Claude Code parser (repo has no pytest).

Builds a synthetic .jsonl in a temp dir, points CLAUDE_PROJECTS at it,
and asserts the parser extracts prose-only messages, drops trivial
sessions, and sets id/title/time correctly.
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

        os.environ["CLAUDE_PROJECTS"] = root
        convs = list(claude.parse("ignored-data-dir"))

    assert len(convs) == 1, f"expected 1 conv (trivial dropped), got {len(convs)}"
    c = convs[0]
    assert c.id == "claude:sess-a", c.id
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
    print("OK: all assertions passed")


if __name__ == "__main__":
    main()
