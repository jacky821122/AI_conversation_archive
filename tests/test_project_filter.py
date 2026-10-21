"""cwd 從 claude/codex 紀錄進到 DB，list/search 能以 --project 篩選，--max-age 會自動重建。"""

import io
import json
import os
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

from ai_archive import cli, store
from ai_archive.parsers import claude, codex


def _write_jsonl(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _claude_session(root, slug, sid, cwd, text):
    _write_jsonl(os.path.join(root, slug, f"{sid}.jsonl"), [
        {"type": "user", "cwd": cwd, "timestamp": "2026-01-01T00:00:00Z",
         "message": {"role": "user", "content": text}},
        {"type": "assistant", "cwd": cwd, "timestamp": "2026-01-01T00:00:05Z",
         "message": {"role": "assistant",
                     "content": [{"type": "text", "text": "收到 " + text}]}},
    ])


def _codex_session(root, sid, cwd, text):
    _write_jsonl(os.path.join(root, f"rollout-x-{sid}.jsonl"), [
        {"type": "session_meta", "timestamp": "2026-01-02T00:00:00Z",
         "payload": {"id": sid, "cwd": cwd}},
        {"type": "event_msg", "timestamp": "2026-01-02T00:00:01Z",
         "payload": {"type": "user_message", "message": text}},
        {"type": "response_item", "timestamp": "2026-01-02T00:00:02Z",
         "payload": {"type": "message", "role": "assistant",
                     "content": [{"type": "output_text", "text": "好的 " + text}]}},
    ])


class ProjectFilter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.claude_root = os.path.join(d, "claude")
        self.codex_root = os.path.join(d, "codex")
        self.out = os.path.join(d, "out")
        _claude_session(self.claude_root, "-w-alpha", "c1", "/w/alpha-repo", "alpha 專案的問題")
        _claude_session(self.claude_root, "-w-beta", "c2", "/w/beta-repo", "beta 專案的問題")
        _codex_session(self.codex_root, "x1", "/w/alpha-repo", "alpha 專案的另一個問題")
        env = {"CLAUDE_PROJECTS": self.claude_root, "CODEX_SESSIONS": self.codex_root,
               "CLAUDE_EXCLUDE_PROMPTS": "", "CODEX_EXCLUDE_PROMPTS": ""}
        self.env = mock.patch.dict(os.environ, env)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def _run(self, *argv):
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["--data", self.tmp.name, "--out", self.out, *argv])
        return buf.getvalue()

    def test_parsers_capture_cwd(self):
        cwds = {c.id: c.cwd for c in claude.parse("")}
        self.assertEqual(cwds, {"claude:c1": "/w/alpha-repo", "claude:c2": "/w/beta-repo"})
        self.assertEqual([c.cwd for c in codex.parse("")], ["/w/alpha-repo"])

    def test_list_and_search_filter_by_project(self):
        self._run("ingest", "--platforms", "claude", "codex")
        listed = json.loads(self._run("list", "--project", "alpha", "--json"))
        self.assertEqual(listed["total"], 2)
        self.assertEqual({i["id"] for i in listed["items"]}, {"claude:c1", "codex:x1"})

        hits = json.loads(self._run("search", "專案的", "--project", "beta", "--json"))
        self.assertEqual({h["conv_id"] for h in hits["items"]}, {"claude:c2"})
        db = os.path.join(self.out, "archive.db")
        self.assertEqual(store.get_conversation(db, "codex:x1")["cwd"], "/w/alpha-repo")

    def test_max_age_rebuilds_stale_db_and_keeps_json_stdout_clean(self):
        self._run("ingest", "--platforms", "claude", "codex")
        db = os.path.join(self.out, "archive.db")
        _claude_session(self.claude_root, "-w-gamma", "c3", "/w/gamma-repo", "gamma 新對話")

        fresh = json.loads(self._run("--max-age", "60", "list", "--project", "gamma", "--json"))
        self.assertEqual(fresh["total"], 0)  # 還新鮮，不重建

        old = time.time() - 2 * 3600
        os.utime(db, (old, old))
        stale = json.loads(self._run("--max-age", "60", "list", "--project", "gamma", "--json"))
        self.assertEqual(stale["total"], 1)  # 過期，自動重建後看得到新 session


if __name__ == "__main__":
    unittest.main()
