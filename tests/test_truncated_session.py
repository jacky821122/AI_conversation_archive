"""Regression tests: a session cut off mid multi-byte character must not crash ingest."""

import json
import tempfile
import unittest
from pathlib import Path

from ai_archive.parsers import claude, codex


def write_truncated(path: Path, records: list[dict]) -> None:
    """完整的 records 之後，接一行截在「中」字第一個位元組的半行。"""
    body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records).encode("utf-8")
    partial = '{"type":"assistant","text":"中'.encode("utf-8")[:-2]
    data = body + partial
    path.write_bytes(data)
    # fixture 本身必須是非法 UTF-8，否則這些測試驗不到東西
    with self_check_raises():
        data.decode("utf-8")


class self_check_raises:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is not UnicodeDecodeError:
            raise AssertionError("fixture should be invalid UTF-8")
        return True


class TruncatedSession(unittest.TestCase):
    def assert_kept_complete_messages(self, conv):
        self.assertIsNotNone(conv)
        self.assertEqual([(m.role, m.text) for m in conv.messages],
                         [("user", "問題"), ("assistant", "回答")])
        self.assertEqual(conv.cwd, "/work")

    def test_claude(self):
        records = [
            {"type": "user", "cwd": "/work", "timestamp": "2026-10-01T00:00:00Z",
             "message": {"role": "user", "content": "問題"}},
            {"type": "assistant", "timestamp": "2026-10-01T00:00:01Z",
             "message": {"role": "assistant",
                         "content": [{"type": "text", "text": "回答"}]}},
        ]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "session.jsonl"
            write_truncated(path, records)
            self.assert_kept_complete_messages(claude._parse_file(str(path)))

    def test_codex(self):
        records = [
            {"type": "session_meta", "timestamp": "2026-10-01T00:00:00Z",
             "payload": {"id": "s1", "cwd": "/work"}},
            {"type": "event_msg", "timestamp": "2026-10-01T00:00:01Z",
             "payload": {"type": "user_message", "message": "問題"}},
            {"type": "event_msg", "timestamp": "2026-10-01T00:00:02Z",
             "payload": {"type": "agent_message", "message": "回答"}},
        ]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "rollout-s1.jsonl"
            write_truncated(path, records)
            self.assert_kept_complete_messages(codex._parse_file(str(path)))


if __name__ == "__main__":
    unittest.main()
