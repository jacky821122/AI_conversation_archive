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


class FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


class RagAnthropicProvider(unittest.TestCase):
    """provider=anthropic 走 Anthropic Messages（httpx 直打）的行為。"""

    def _fake_post(self, captured: dict):
        def post(url, headers=None, json=None, timeout=None, verify=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            captured["verify"] = verify
            return FakeResponse(
                {"content": [{"type": "text", "text": "gw-ok"}]}
            )

        return post

    def anthropic_env(self) -> dict:
        return {
            "RAG_PROVIDER": "anthropic",
            "ANTHROPIC_BASE_URL": "https://gw.example/Anthropic",
            "RAG_ANTHROPIC_MODEL": "Claude-Sonnet-4.6",
            "ANTHROPIC_CUSTOM_HEADERS": "Ocp-Apim-Subscription-Key: sub-123",
        }

    def test_complete_uses_messages_endpoint_and_extracts_text(self):
        captured: dict = {}
        with (
            mock.patch.dict(os.environ, self.anthropic_env(), clear=True),
            mock.patch("httpx.post", self._fake_post(captured)),
        ):
            out = rag.complete([
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "hi"},
            ])

        self.assertEqual(out, "gw-ok")
        self.assertEqual(captured["url"], "https://gw.example/Anthropic/v1/messages")
        self.assertEqual(captured["json"]["model"], "Claude-Sonnet-4.6")
        # system 應被抽離 messages、放進 top-level system 欄位
        self.assertEqual(captured["json"]["system"], "sys")
        self.assertEqual(captured["json"]["messages"],
                         [{"role": "user", "content": "hi"}])
        # 自訂 header 應被解析注入
        self.assertEqual(captured["headers"]["Ocp-Apim-Subscription-Key"], "sub-123")
        self.assertEqual(captured["headers"]["anthropic-version"], "2023-06-01")

    def test_complete_preserves_explicit_model_override(self):
        captured: dict = {}
        with (
            mock.patch.dict(os.environ, self.anthropic_env(), clear=True),
            mock.patch("httpx.post", self._fake_post(captured)),
        ):
            rag.complete([{"role": "user", "content": "hi"}], model="Claude-Opus-4.8")

        self.assertEqual(captured["json"]["model"], "Claude-Opus-4.8")

    def test_resolve_default_model_is_provider_aware(self):
        with mock.patch.dict(os.environ, self.anthropic_env(), clear=True):
            self.assertEqual(rag.resolve_default_model(), "Claude-Sonnet-4.6")

    def test_shell_anthropic_model_does_not_override_rag_model(self):
        """Claude Code shell 的 ANTHROPIC_MODEL 不該蓋掉館長專屬模型。"""
        env = self.anthropic_env()
        env["ANTHROPIC_MODEL"] = "Claude-Opus-4.8"  # 模擬 shell 注入
        captured: dict = {}
        with (
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch("httpx.post", self._fake_post(captured)),
        ):
            rag.complete([{"role": "user", "content": "hi"}])
        self.assertEqual(captured["json"]["model"], "Claude-Sonnet-4.6")

    def test_missing_key_raises(self):
        env = {"RAG_PROVIDER": "anthropic",
               "ANTHROPIC_BASE_URL": "https://gw.example/Anthropic"}
        with (
            mock.patch.dict(os.environ, env, clear=True),
            self.assertRaises(SystemExit),
        ):
            rag.complete([{"role": "user", "content": "hi"}])


if __name__ == "__main__":
    unittest.main()
