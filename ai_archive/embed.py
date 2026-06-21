"""對話分塊（chunking）+ 本地 bge-m3 向量化。

兩個獨立關注點，刻意拆開讓分塊邏輯零模型依賴、可單測：

1. 分塊：把一段對話攤平成「訊息單元」（過長訊息先切到 <= MAX_UNIT_CHARS），
   再用滑動視窗貪婪打包成 ~TARGET_CHARS 的 chunk，相鄰 chunk 重疊 ~OVERLAP_CHARS
   以免語意被切斷在邊界。每個 chunk 帶 conv_id / platform / title / time /
   涵蓋的訊息 idx 範圍，供之後檢索附出處、回跳原對話。
2. Embedder：lazy 載入 sentence-transformers 的 BAAI/bge-m3（繁中佳、免 instruction
   前綴），normalize 後輸出 float32；cosine 相似度即點積。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator

from .schema import Conversation

# 分塊參數（字元為單位，對 CJK 比 token 直覺）。bge-m3 上限 8192 token，綽綽有餘。
TARGET_CHARS = 1000   # 每個 chunk 的目標大小
OVERLAP_CHARS = 200   # 相鄰 chunk 重疊量
MAX_UNIT_CHARS = 1000  # 單一訊息單元上限（超過先硬切）

DEFAULT_MODEL = "BAAI/bge-m3"
EMBED_DIM = 1024  # bge-m3 輸出維度


@dataclass
class Chunk:
    conv_id: str
    platform: str
    title: str
    time: float | None
    msg_start: int  # chunk 涵蓋的第一個訊息 idx
    msg_end: int    # 最後一個訊息 idx
    text: str       # 含 role 標籤的可讀內容（同時拿去 embed 與顯示）


def _split_text(text: str, max_chars: int) -> list[str]:
    """把一則訊息切成 <= max_chars 的片段：先依空行分段、貪婪合併小段，
    過長的段落再硬切。"""
    pieces: list[str] = []
    cur = ""
    for para in re.split(r"\n{2,}", text):
        para = para.strip()
        if not para:
            continue
        while len(para) > max_chars:
            if cur:
                pieces.append(cur)
                cur = ""
            pieces.append(para[:max_chars])
            para = para[max_chars:]
        if not cur:
            cur = para
        elif len(cur) + 1 + len(para) <= max_chars:
            cur += "\n" + para
        else:
            pieces.append(cur)
            cur = para
    if cur:
        pieces.append(cur)
    return pieces


def _units(conv: Conversation) -> list[tuple[int, str, str]]:
    """攤平成單元 (msg_idx, role, piece_text)，過長訊息先切片。"""
    out: list[tuple[int, str, str]] = []
    for idx, m in enumerate(conv.messages):
        text = (m.text or "").strip()
        if not text:
            continue
        for piece in _split_text(text, MAX_UNIT_CHARS):
            out.append((idx, m.role, piece))
    return out


def _render(units: list[tuple[int, str, str]], title: str) -> str:
    """把單元組成 chunk 文字：標題作輕量脈絡 + 每單元加 role 標籤。"""
    body = "\n".join(f"{role}: {piece}" for _, role, piece in units)
    title = (title or "").strip()
    return f"【{title}】\n{body}" if title else body


def iter_chunks(conv: Conversation,
                target_chars: int = TARGET_CHARS,
                overlap_chars: int = OVERLAP_CHARS) -> Iterator[Chunk]:
    """對單段對話產生滑動視窗 chunk。"""
    units = _units(conv)
    n = len(units)
    if n == 0:
        return
    i = 0
    while i < n:
        cur: list[tuple[int, str, str]] = []
        cur_len = 0
        j = i
        while j < n:
            ul = len(units[j][2])
            if cur and cur_len + ul > target_chars:
                break
            cur.append(units[j])
            cur_len += ul
            j += 1
        idxs = [u[0] for u in cur]
        yield Chunk(
            conv_id=conv.id,
            platform=conv.platform,
            title=conv.title,
            time=conv.create_time,
            msg_start=min(idxs),
            msg_end=max(idxs),
            text=_render(cur, conv.title),
        )
        if j >= n:
            break
        # 回退讓下一個 chunk 由尾端 ~overlap_chars 的單元接續
        back = 0
        k = j - 1
        while k > i and back + len(units[k][2]) <= overlap_chars:
            back += len(units[k][2])
            k -= 1
        i = k + 1 if k + 1 > i else j


def chunk_all(convs: Iterator[Conversation]) -> Iterator[Chunk]:
    for c in convs:
        yield from iter_chunks(c)


class Embedder:
    """bge-m3 包裝，lazy 載入（避免 import 就拖 torch）。"""

    def __init__(self, model_name: str = DEFAULT_MODEL, device: str | None = None):
        self.model_name = model_name
        self.device = device  # None = 自動（有 CUDA 用 GPU，否則 CPU）
        self._model = None

    def _resolve_device(self) -> str:
        if self.device:
            return self.device
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except Exception:
            return "cpu"

    def _load(self):
        from sentence_transformers import SentenceTransformer  # 延後 import
        self.device = self._resolve_device()
        self._model = SentenceTransformer(self.model_name, device=self.device)

    @property
    def device_str(self) -> str:
        if self._model is None:
            self._load()
        return str(self._model.device)

    @property
    def dim(self) -> int:
        if self._model is None:
            self._load()
        return self._model.get_sentence_embedding_dimension()

    def encode(self, texts: list[str], batch_size: int = 32,
               show_progress: bool = False):
        """回傳 (n, dim) 的 float32 ndarray，已 L2 normalize。"""
        if self._model is None:
            self._load()
        vecs = self._model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=show_progress,
            convert_to_numpy=True,
        )
        return vecs.astype("float32")

    def encode_one(self, text: str):
        return self.encode([text])[0]
