"""Parser registry：platform -> parse(data_dir) -> Iterator[Conversation]。

新增平台（例如未來的另一種 Gemini 匯出）只要寫一個模組、在這裡註冊即可，
ingest / 後續 Phase B/C 完全不用改。
"""

from __future__ import annotations

from typing import Callable, Iterator

from ..schema import Conversation
from . import chatgpt, grok, gemini

ParseFn = Callable[[str], Iterator[Conversation]]

REGISTRY: dict[str, ParseFn] = {
    "chatgpt": chatgpt.parse,
    "grok": grok.parse,
    "gemini": gemini.parse,
}


def parse_all(data_dir: str, platforms: list[str] | None = None) -> Iterator[Conversation]:
    for name in (platforms or list(REGISTRY)):
        yield from REGISTRY[name](data_dir)
