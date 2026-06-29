"""Grok parser regression tests."""

import json
import tempfile
import unittest
from pathlib import Path

from ai_archive.parsers import grok


class GrokParser(unittest.TestCase):
    def test_unknown_senders_are_skipped(self):
        data = {
            "conversations": [
                {
                    "conversation": {"id": "c1", "title": "Sender roles"},
                    "responses": [
                        {"response": {"sender": "human", "message": "hello"}},
                        {"response": {"sender": "ASSISTANT", "message": "hi"}},
                        {"response": {"sender": "assistant", "message": "lowercase hi"}},
                        {"response": {"sender": "system", "message": "do not ingest"}},
                        {"response": {"sender": "tool", "message": "tool output"}},
                        {"response": {"message": "missing sender"}},
                    ],
                }
            ]
        }

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "prod-grok-backend.json"
            path.write_text(json.dumps(data), encoding="utf-8")

            convs = list(grok.parse(td))

        self.assertEqual(len(convs), 1)
        self.assertEqual([m.role for m in convs[0].messages],
                         ["user", "assistant", "assistant"])
        self.assertEqual([m.text for m in convs[0].messages],
                         ["hello", "hi", "lowercase hi"])


if __name__ == "__main__":
    unittest.main()
