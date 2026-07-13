"""store.build 的去重行為：同 id 出現多次（新舊快照重疊）時保留較新的一份。"""

import os
import sqlite3
import tempfile
import unittest

from ai_archive import store
from ai_archive.schema import Conversation, Message


class StoreBuildDedupe(unittest.TestCase):
    def test_duplicate_id_keeps_newer_update_time(self):
        old = Conversation(
            id="chatgpt:abc", platform="chatgpt", title="舊版",
            create_time=1.0, update_time=100.0,
            messages=[Message(role="user", text="舊訊息")],
        )
        new = Conversation(
            id="chatgpt:abc", platform="chatgpt", title="新版",
            create_time=1.0, update_time=200.0,
            messages=[Message(role="user", text="新訊息一"),
                     Message(role="assistant", text="新訊息二")],
        )
        with tempfile.TemporaryDirectory() as d:
            db = os.path.join(d, "archive.db")
            # 順序不影響結果：先新後舊、先舊後新都該保留 update_time=200 那份
            stats = store.build(iter([old, new]), db)
            self.assertEqual(stats["conversations"], 1)
            self.assertEqual(stats["messages"], 2)

            con = sqlite3.connect(db)
            title = con.execute(
                "SELECT title FROM conversations WHERE id = ?", ("chatgpt:abc",)
            ).fetchone()[0]
            self.assertEqual(title, "新版")
            con.close()

            stats2 = store.build(iter([new, old]), db)
            self.assertEqual(stats2["conversations"], 1)
            con = sqlite3.connect(db)
            title = con.execute(
                "SELECT title FROM conversations WHERE id = ?", ("chatgpt:abc",)
            ).fetchone()[0]
            self.assertEqual(title, "新版")
            con.close()


if __name__ == "__main__":
    unittest.main()
