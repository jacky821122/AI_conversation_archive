"""純 stdlib 合成 fixture：Codex parser、CLI 匯入與下游讀取回歸檢查。"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from ai_archive import cli, store
from ai_archive.embed import chunk_all
from ai_archive.parsers import REGISTRY, codex
from ai_archive.schema import read_jsonl


def record(kind: str, payload: dict, second: int = 0) -> dict:
    return {
        "type": kind, "payload": payload,
        "timestamp": f"2026-10-01T00:00:{second:02d}Z",
    }


def message(role: str, text: str, second: int = 1, **extra) -> dict:
    return record("response_item", {
        "type": "message", "role": role,
        "content": [{"type": "input_text" if role == "user" else "output_text",
                     "text": text}],
        **extra,
    }, second)


def write_session(root: Path, name: str, records: list[dict]) -> Path:
    path = root / f"rollout-{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in records) + "\n")
    return path


def main() -> None:
    assert "codex" in REGISTRY
    with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
        "CODEX_HOME": directory,
        "CODEX_SESSIONS": "",
        "CODEX_EXCLUDE_PROMPTS": "",
    }):
        home = Path(directory)
        sessions = home / "sessions" / "2026" / "10" / "01"
        prompt = "測試本機 Codex 匯入"
        normal = write_session(sessions, "filename-is-not-the-id", [
            record("session_meta", {"id": "normal", "source": "cli"}),
            message("developer", "private instructions"),
            record("response_item", {"type": "message", "role": [], "content": "bad-role"}),
            record("event_msg", {"type": "item_completed", "item": {"type": []}}),
            message("user", "# AGENTS.md instructions for /example"),
            message("user", "<environment_context>injected</environment_context>"),
            message("user", "<task-notification>background task</task-notification>"),
            message("user", prompt, 2),
            record("event_msg", {"type": "user_message", "message": prompt}, 2),
            message("user", "<skill>injected skill</skill>"),
            message("assistant", "private reasoning", channel="analysis"),
            record("response_item", {"type": "reasoning", "summary": "private reasoning"}),
            record("response_item", {"type": "function_call", "arguments": "private tool input"}),
            record("response_item", {"type": "function_call_output", "output": "private tool output"}),
            record("response_item", {
                "type": "message", "role": "assistant", "phase": "commentary",
                "content": [{"type": "output_text", "text": "第一段"},
                            {"type": "output_text", "text": "第二段"},
                            {"type": "image", "image_url": "private image"}],
            }, 3),
            record("event_msg", {"type": "agent_message", "message": "第一段\n第二段"}, 3),
            message("user", prompt, 4),
            record("event_msg", {"type": "user_message", "message": prompt}, 4),
            message("assistant", "API Error: 只是討論錯誤訊息，不是操作事件", 5),
            record("compacted", {"message": "compaction summary", "replacement_history": []}),
        ])
        with normal.open("a") as stream:
            stream.write('\nnot-json\nnull\n[]\n{"payload": null}\n{"type":')
        conversation = codex._parse_file(str(normal))
        assert conversation is not None
        assert conversation.id == "codex:normal"
        assert conversation.platform == "codex"
        assert conversation.title == prompt
        assert [item.text for item in conversation.messages] == [
            prompt, "第一段\n第二段", prompt,
            "API Error: 只是討論錯誤訊息，不是操作事件",
        ]
        assert [item.role for item in conversation.messages] == [
            "user", "assistant", "user", "assistant",
        ]
        assert conversation.update_time - conversation.create_time == 3
        reply_path = write_session(sessions, "menu-reply", [
            record("session_meta", {"id": "menu-reply", "source": "cli"}),
            message("user", "選擇處理方式", 1),
            record("event_msg", {"type": "user_message", "message": "選擇處理方式"}, 1),
            message("assistant", "請從選單選擇", 2),
            message("user", '<send_user_message_question_reply>\n'
                    '[{"question":"選擇處理方式","answer":"保留現有資料"}]\n'
                    '</send_user_message_question_reply>', 3),
            message("assistant", "已保留", 4),
        ])
        assert [item.text for item in codex._parse_file(str(reply_path)).messages] == [
            "選擇處理方式", "請從選單選擇", "保留現有資料", "已保留",
        ]
        assert codex._text("<send_user_message_question_reply>bad-json", "user") == ""
        assert codex._text('<send_user_message_question_reply>[{"answer":" "},{"answer":""}]'
                           '</send_user_message_question_reply>', "user") == ""
        with reply_path.open("a") as stream:
            stream.write(json.dumps(record("response_item", {
                "type": "message", "role": "user",
                "content": '<send_user_message_question_reply>'
                           '[{"answer":"繼續保留"}]</send_user_message_question_reply>',
            }, 5)) + "\n")
        assert codex._parse_file(str(reply_path)).messages[-1].text == "繼續保留"

        canonical = write_session(sessions, "canonical", [
            record("session_meta", {"id": "canonical", "source": "vscode"}),
            message("user", "# AGENTS.md instructions for /example"),
            message("user", "環境文字\n真正發言", 6),
            record("event_msg", {"type": "item_completed", "item": {
                "type": "UserMessage", "id": "user-id",
                "content": [{"type": "text", "text": "真正發言"},
                            {"type": "image", "url": "private image"}],
            }}, 6),
            message("assistant", "已處理", 7),
            record("event_msg", {"type": "item_completed", "item": {
                "type": "AgentMessage", "content": [{"type": "text", "text": "已處理"}],
            }}, 7),
        ])
        assert [item.text for item in codex._parse_file(str(canonical)).messages] == [
            "真正發言", "已處理",
        ]

        legacy = write_session(home / "archived_sessions", "legacy", [
            record("session_meta", {"session_id": "legacy", "source": "exec"}),
            record("response_item", {"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": "# AGENTS.md instructions for /example"},
                {"type": "input_text", "text": "舊版文字保留"},
                {"type": "input_text", "text": "<environment_context>injected"},
            ]}, 8),
            record("response_item", {"type": "message", "role": "assistant",
                                     "content": "舊版回答"}, 9),
        ])
        assert [item.text for item in codex._parse_file(str(legacy)).messages] == [
            "舊版文字保留", "舊版回答",
        ]
        event_only = write_session(sessions, "event-only", [
            record("session_meta", {"id": "event-only", "source": "cli"}),
            record("event_msg", {"type": "user_message", "message": "只有事件的問題"}),
            record("event_msg", {"type": "item_completed", "item": {
                "type": "AgentMessage", "content": [{"type": "text", "text": "事件回答"}],
            }}),
        ])
        assert len(codex._parse_file(str(event_only)).messages) == 2
        for name, records in {
            "no-user": [message("assistant", "沒有使用者")],
            "no-answer": [message("user", "尚未回答")],
            "noise": [message("user", "<turn_aborted>interrupted"), message("assistant", "雜訊")],
        }.items():
            path = write_session(sessions, name, [
                record("session_meta", {"id": name}), *records,
            ])
            assert codex._parse_file(str(path)) is None
        child = write_session(sessions, "subagent", [
            record("session_meta", {"id": "child", "source": {"subagent": {"thread_spawn": {}}}}),
            message("user", "委派工作"), message("assistant", "委派回答"),
        ])
        assert codex._parse_file(str(child)) is None
        started = lambda turn: record("event_msg", {"type": "task_started", "turn_id": turn})
        imported = [
            record("session_meta", {"id": "imported", "source": "cli"}),
            started("external-import-turn-1"),
            record("event_msg", {"type": "user_message", "message": "從 Claude 匯入的舊問題"}),
            message("user", "從 Claude 匯入的舊問題"), message("assistant", "匯入的舊回答"),
        ]
        only_import = write_session(home / "import-fixtures", "import-only", imported)
        assert codex._parse_file(str(only_import)) is None
        continued = write_session(home / "import-fixtures", "import-continued", [
            *imported, started("turn-2"),
            record("event_msg", {"type": "user_message", "message": "匯入後的新問題"}, 8),
            message("user", "匯入後的新問題", 8), message("assistant", "新回答", 9),
        ])
        assert [item.text for item in codex._parse_file(str(continued)).messages] == [
            "匯入後的新問題", "新回答",
        ]
        only_import.unlink()
        continued.unlink()
        with patch.dict(os.environ, {"CODEX_EXCLUDE_PROMPTS": " irrelevant, 測試本機 "}):
            assert codex._parse_file(str(normal)) is None
            assert codex._parse_file(str(canonical)) is not None
        assert legacy.as_posix() in codex.discover("ignored")
        with patch.dict(os.environ, {"CODEX_SESSIONS": str(sessions)}):
            assert legacy.as_posix() not in codex.discover("ignored")
        with patch.dict(os.environ, {"CODEX_SESSIONS": str(home / "missing")}):
            assert list(codex.parse("ignored")) == []
        expected = {"codex:normal", "codex:canonical", "codex:legacy", "codex:event-only", "codex:menu-reply"}
        assert {item.id for item in codex.parse("ignored")} == expected
        assert all(chunk.platform == "codex" for chunk in chunk_all(codex.parse("ignored")))

        output = home / "output"
        arguments = ["--data", str(home / "missing"), "--out", str(output),
                     "ingest", "--platforms", "codex", "--codex-path", str(home),
                     "--codex-exclude-prompts", "not-a-real-prefix"]
        source_hash = hashlib.sha256(normal.read_bytes()).hexdigest()
        with contextlib.redirect_stdout(io.StringIO()):
            cli.main(arguments)
            first = (output / "normalized.jsonl").read_bytes()
            cli.main(arguments)
        assert first == (output / "normalized.jsonl").read_bytes()
        assert source_hash == hashlib.sha256(normal.read_bytes()).hexdigest()
        assert {item.id for item in read_jsonl(str(output / "normalized.jsonl"))} == expected
        db = str(output / "archive.db")
        assert store.stats(db)["per_platform"] == {"codex": 5}
        assert len(store.list_conversations(db, platform="codex")) == 5
        assert store.get_conversation(db, "codex:normal")["messages"][0]["text"] == prompt
        assert store.search(db, "本機 Codex", platform="codex")
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            cli.main(["--out", str(output), "list", "--platform", "codex", "--json"])
        assert json.loads(captured.getvalue())["total"] == 5
    print("OK: Codex parser, CLI, idempotency, local search and chunking passed")


if __name__ == "__main__":
    main()
