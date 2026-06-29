"""API model lifecycle regressions.

Run with:

    PYTHONPATH=. python -m unittest tests.test_api_model_lifecycle -v
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest

from fastapi import HTTPException

from ai_archive import api, rag


class ApiAskModelLifecycle(unittest.TestCase):
    def setUp(self):
        self._orig_ask_token = api.ASK_TOKEN
        self._orig_db_path = api.DB_PATH
        self._orig_embedder = api._embedder
        self._orig_last_used = api._last_used
        self._orig_retrieve = rag.retrieve
        self._orig_build_context = rag.build_context
        self._orig_complete = rag.complete
        self._orig_resolve_default_model = rag.resolve_default_model

    def tearDown(self):
        api.ASK_TOKEN = self._orig_ask_token
        api.DB_PATH = self._orig_db_path
        api._embedder = self._orig_embedder
        api._last_used = self._orig_last_used
        rag.retrieve = self._orig_retrieve
        rag.build_context = self._orig_build_context
        rag.complete = self._orig_complete
        rag.resolve_default_model = self._orig_resolve_default_model

    def test_ask_retrieval_blocks_release_but_completion_does_not(self):
        api.ASK_TOKEN = "secret"
        sentinel_embedder = object()
        api._embedder = sentinel_embedder

        with tempfile.TemporaryDirectory() as tmp:
            api.DB_PATH = os.path.join(tmp, "archive.db")
            open(api.DB_PATH, "w", encoding="utf-8").close()

            retrieve_entered = threading.Event()
            allow_retrieve_return = threading.Event()
            release_finished = threading.Event()
            complete_saw_unlocked = threading.Event()

            chunks = [{
                "platform": "chatgpt",
                "title": "T",
                "time": None,
                "conv_id": "c1",
                "msg_start": 0,
                "msg_end": 1,
                "text": "assistant: answer",
            }]

            def fake_retrieve(question, out_dir, top_k, embedder):
                self.assertEqual(question, "q")
                self.assertEqual(out_dir, tmp)
                self.assertEqual(top_k, 3)
                self.assertIs(embedder, sentinel_embedder)
                retrieve_entered.set()
                self.assertTrue(allow_retrieve_return.wait(timeout=2))
                return chunks

            def fake_complete(messages, model, max_tokens):
                self.assertTrue(release_finished.wait(timeout=2))
                acquired = api._model_lock.acquire(blocking=False)
                try:
                    if acquired:
                        complete_saw_unlocked.set()
                finally:
                    if acquired:
                        api._model_lock.release()
                self.assertEqual(model, "resolved-model")
                self.assertEqual(max_tokens, 4096)
                self.assertEqual(messages[0]["role"], "system")
                return "done"

            rag.retrieve = fake_retrieve
            rag.build_context = lambda got_chunks: "context"
            rag.complete = fake_complete
            rag.resolve_default_model = lambda: "resolved-model"

            ask_result = {}
            ask_errors = []

            def run_ask():
                try:
                    ask_result.update(
                        api.api_ask(api.AskBody(question="q", top_k=3),
                                    x_ask_token="secret")
                    )
                except Exception as exc:
                    ask_errors.append(exc)

            ask_thread = threading.Thread(target=run_ask)
            ask_thread.start()
            self.assertTrue(retrieve_entered.wait(timeout=2))

            release_thread = threading.Thread(
                target=lambda: (api._model_release(), release_finished.set())
            )
            release_thread.start()
            time.sleep(0.05)
            self.assertFalse(release_finished.is_set())
            self.assertIs(api._embedder, sentinel_embedder)

            allow_retrieve_return.set()
            ask_thread.join(timeout=2)
            release_thread.join(timeout=2)

            self.assertFalse(ask_thread.is_alive())
            self.assertFalse(release_thread.is_alive())
            self.assertEqual(ask_errors, [])
            self.assertTrue(release_finished.is_set())
            self.assertTrue(complete_saw_unlocked.is_set())
            self.assertEqual(ask_result["answer"], "done")
            self.assertEqual(ask_result["sources"][0]["conv_id"], "c1")

    def test_ask_still_returns_409_when_model_is_not_loaded(self):
        api.ASK_TOKEN = "secret"
        api._embedder = None

        with tempfile.TemporaryDirectory() as tmp:
            api.DB_PATH = os.path.join(tmp, "archive.db")
            open(api.DB_PATH, "w", encoding="utf-8").close()

            def fail_retrieve(*args, **kwargs):
                raise AssertionError("retrieve should not run without a loaded model")

            rag.retrieve = fail_retrieve

            with self.assertRaises(HTTPException) as caught:
                api.api_ask(api.AskBody(question="q"), x_ask_token="secret")

            self.assertEqual(caught.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
