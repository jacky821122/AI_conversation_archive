"""Claude Code (本機 session 紀錄) parser。

紀錄存在 ~/.claude/projects/<slugified-cwd>/<sessionId>.jsonl，一個工作目錄
一個資料夾、一個檔 = 一個 session。每行是一筆 typed JSON record，只有
type 為 user/assistant 且帶 message 者含對話文字。

prose only：message.content 為字串直接取；為 block 陣列則只留 type=="text"
的 block（丟掉 thinking / tool_use / tool_result）。一個 session = 一個
Conversation；丟掉「沒有任何含文字 user 訊息」的 trivial session。

**queued prompt**：使用者趁 Claude 還在跑時打字送出的訊息，CLI 不會寫成
type=="user" 的記錄，只留 type=="attachment" 且 attachment.type=="queued_command"
的那一筆（帶 prompt 欄）。只認 commandMode=="prompt"（真人輸入）；
commandMode=="task-notification" 是背景任務完成通知，機器產生的，不收。
不收會造成「真人發言消失、只剩 assistant 自言自語」，語料庫無法重現對話。

同理，CLI 塞進 user 角色的操作紀錄（<task-notification>、斜線指令叫用與其 stdout、
caveat 樣板、system-reminder）也不是人講的話，一併濾掉；見 _UI_NOISE_PREFIXES。

另外把開頭為 "API Error:" 的 assistant 訊息當噪音濾掉（網路/設定壞掉時的回應）；
濾掉後若整個 session 沒有任何 assistant 文字，視為「問了但沒得到有用回應」的
廢 session 一併丟棄。用 startswith 精準命中真 error，不會誤殺內文討論 API error
的真對話。

噪音排除（headless agent 的 cron run / healthcheck ping）：headless 用法（如排程
餵入大段 agent system prompt、或 warmup/健康檢查 ping）會在同一個工作目錄留下大量
雜訊 session，且重要輸出在別處。判別子＝**首則 user 訊息的前綴**：以 CLAUDE_EXCLUDE_PROMPTS
（逗號分隔）任一前綴開頭者整段丟棄。用內容判別（非資料夾），故同一專案目錄下的「真
人手動開發」session 不受影響。個人前綴清單放本機 env/.env（gitignored），公開碼維持
泛用、不寫死特定專案名。

來源 root 由 CLAUDE_PROJECTS 環境變數覆蓋，否則用 ~/.claude/projects。
與其他 parser 不同，本 parser 不讀傳入的 data_dir。
"""

from __future__ import annotations

import glob
import json
import os
from typing import Iterator

from ..schema import Conversation, Message
from ._util import iso_to_epoch

_DEFAULT_ROOT = "~/.claude/projects"

# CLI 自己塞進 user 角色的操作紀錄，不是人講的話：斜線指令的叫用（/exit、/model、
# /clear…）、它們的 stdout、告訴模型「別回應這些」的樣板 caveat、harness 的
# system-reminder。留著會在對話尾端堆一坨雜訊，也讓「使用者說了什麼」失真。
#
# 刻意**不含** <bash-input> / <bash-stdout>：那是使用者用 `!` 主動把指令與輸出送進
# 對話、模型也據此回應的內容，屬於對話的一部分，拿掉會跟漏掉發言一樣破壞重現性。
_UI_NOISE_PREFIXES = (
    "<task-notification>",     # 背景任務完成通知（harness 注入）
    "<local-command-caveat>",
    "<local-command-stdout>",
    "<command-name>",
    "<command-message>",
    "<command-args>",
    "<system-reminder>",
)


def _root() -> str:
    return os.path.expanduser(
        os.environ.get("CLAUDE_PROJECTS") or _DEFAULT_ROOT
    )


def _exclude_prefixes() -> tuple[str, ...]:
    """CLAUDE_EXCLUDE_PROMPTS（逗號分隔）→ 首則 user 訊息前綴黑名單。

    命中者＝headless agent 的 cron run / healthcheck ping，整段視為噪音丟棄。
    空值（預設）＝不排除任何東西，公開碼行為中性；個人清單放本機 env/.env。
    """
    raw = os.environ.get("CLAUDE_EXCLUDE_PROMPTS", "")
    return tuple(p.strip() for p in raw.split(",") if p.strip())


def _text_from_content(content) -> str:
    """prose only：字串直接回；block 陣列只留 text block 合併。"""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            b["text"] for b in content
            if isinstance(b, dict) and b.get("type") == "text" and b.get("text")
        ]
        return "\n".join(parts).strip()
    return ""


def _queued_prompt(rec: dict) -> tuple[str, str] | None:
    """真人 queued prompt → (text, timestamp)；其餘（含背景通知）回 None。"""
    if rec.get("type") != "attachment":
        return None
    att = rec.get("attachment")
    if not isinstance(att, dict) or att.get("type") != "queued_command":
        return None
    if att.get("commandMode") != "prompt":
        return None
    text = (att.get("prompt") or "").strip()
    if not text:
        return None
    return text, att.get("timestamp") or rec.get("timestamp") or ""


def _parse_file(path: str) -> Conversation | None:
    session_id = os.path.splitext(os.path.basename(path))[0]
    messages: list[Message] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            queued = _queued_prompt(rec)
            if queued is not None:
                # 排隊送出的真人發言；沒有對應的 type=="user" 記錄，這裡是唯一來源
                messages.append(Message(
                    role="user", text=queued[0], time=iso_to_epoch(queued[1])
                ))
                continue
            if rec.get("type") not in ("user", "assistant"):
                continue
            msg = rec.get("message")
            if not isinstance(msg, dict):
                continue
            text = _text_from_content(msg.get("content"))
            if not text:
                continue
            role = "user" if rec.get("type") == "user" else "assistant"
            # API Error 開頭的 assistant 回應＝噪音（網路/設定壞掉），丟掉
            if role == "assistant" and text.startswith("API Error:"):
                continue
            # CLI 操作紀錄（斜線指令、其 stdout、caveat、通知）不是人講的話，丟掉
            if role == "user" and text.startswith(_UI_NOISE_PREFIXES):
                continue
            t = iso_to_epoch(rec.get("timestamp") or "")
            messages.append(Message(role=role, text=text, time=t))

    # drop trivial：沒有任何含文字的 user 訊息就丟棄
    user_msgs = [m for m in messages if m.role == "user" and m.text]
    if not user_msgs:
        return None
    # 首則 user 訊息命中排除前綴＝headless cron run / ping 噪音，整段丟棄
    excl = _exclude_prefixes()
    if excl and user_msgs[0].text.startswith(excl):
        return None
    # 濾掉 API Error 後若無任何 assistant 文字＝問了但沒得到有用回應，丟棄
    if not any(m.role == "assistant" for m in messages):
        return None

    times = [m.time for m in messages if m.time]
    title = user_msgs[0].text.replace("\n", " ")[:60]
    return Conversation(
        id=f"claude:{session_id}",
        platform="claude",
        title=title or session_id,
        create_time=min(times) if times else None,
        update_time=max(times) if times else None,
        messages=messages,
    )


def discover(data_dir: str) -> list[str]:
    # data_dir 忽略；Claude Code 紀錄在 ~/.claude/projects（或 CLAUDE_PROJECTS）
    root = _root()
    if not os.path.isdir(root):
        return []
    return sorted(glob.glob(os.path.join(root, "*", "*.jsonl")))


def parse(data_dir: str) -> Iterator[Conversation]:
    for path in discover(data_dir):
        c = _parse_file(path)
        if c is not None:
            yield c
