"""RAG generation model config regression tests.

These tests use fake dotenv/openai modules so they do not require network access
or the optional RAG dependencies to be installed.
"""

import os
import sys
import types
import unittest
from unittest import mock

from ai_archive import rag


class FakeOpenAI:
    init_kwargs: dict | None = None
    create_kwargs: dict | None = None

    def __init__(self, **kwargs):
        type(self).init_kwargs = kwargs
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create)
        )

    def _create(self, **kwargs):
        type(self).create_kwargs = kwargs
        msg = types.SimpleNamespace(content="ok")
        choice = types.SimpleNamespace(message=msg)
        return types.SimpleNamespace(choices=[choice])


def fake_dotenv_module() -> types.ModuleType:
    mod = types.ModuleType("dotenv")

    def load_dotenv() -> None:
        os.environ["AGNES_MODEL"] = "env-model"
        os.environ["AGNES_API_KEY"] = "env-key"
        os.environ["AGNES_BASE_URL"] = "https://env.example/v1"

    mod.load_dotenv = load_dotenv
    return mod


def fake_openai_module() -> types.ModuleType:
    mod = types.ModuleType("openai")
    mod.OpenAI = FakeOpenAI
    return mod


class RagModelConfig(unittest.TestCase):
    def setUp(self):
        FakeOpenAI.init_kwargs = None
        FakeOpenAI.create_kwargs = None

    def fake_modules(self):
        return mock.patch.dict(
            sys.modules,
            {"dotenv": fake_dotenv_module(), "openai": fake_openai_module()},
        )

    def test_complete_resolves_default_model_after_dotenv_load(self):
        with mock.patch.dict(os.environ, {}, clear=True), self.fake_modules():
            self.assertEqual(rag.complete([{"role": "user", "content": "hi"}]), "ok")

        self.assertEqual(FakeOpenAI.create_kwargs["model"], "env-model")
        self.assertEqual(FakeOpenAI.init_kwargs["api_key"], "env-key")
        self.assertEqual(FakeOpenAI.init_kwargs["base_url"], "https://env.example/v1")

    def test_complete_preserves_explicit_model_override(self):
        with mock.patch.dict(os.environ, {}, clear=True), self.fake_modules():
            rag.complete([{"role": "user", "content": "hi"}], model="explicit-model")

        self.assertEqual(FakeOpenAI.create_kwargs["model"], "explicit-model")

    def test_ask_reports_runtime_default_model_when_omitted(self):
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            self.fake_modules(),
            mock.patch.object(rag, "retrieve", return_value=[]),
        ):
            res = rag.ask("question")

        self.assertEqual(res["model"], "env-model")


if __name__ == "__main__":
    unittest.main()
