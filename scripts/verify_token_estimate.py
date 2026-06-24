"""Standalone regression check for store.estimate_tokens (repo has no pytest).

Run from the repo root:
    PYTHONPATH=. python scripts/verify_token_estimate.py
"""

from ai_archive.store import estimate_tokens


def main():
    # 純 ASCII：4 字元 ≈ 1 token，無條件進位。
    assert estimate_tokens("abcd") == 1, estimate_tokens("abcd")
    assert estimate_tokens("abcde") == 2, estimate_tokens("abcde")
    # 純 CJK：1 字 ≈ 1 token。
    assert estimate_tokens("你好嗎") == 3, estimate_tokens("你好嗎")
    # 混合：CJK 字數 + ceil(非 CJK 字元數 / 4)。
    # "你好abcd" → 2 CJK + ceil(4/4)=1 → 3
    assert estimate_tokens("你好abcd") == 3, estimate_tokens("你好abcd")
    # 空字串 → 0。
    assert estimate_tokens("") == 0, estimate_tokens("")
    # 空白等非 CJK 也計入非 CJK 桶："a b"（3 字元）→ ceil(3/4)=1
    assert estimate_tokens("a b") == 1, estimate_tokens("a b")

    import tempfile, os
    from ai_archive.schema import Conversation, Message
    from ai_archive import store

    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "t.db")
        convs = [
            Conversation(
                id="claude:x", platform="claude", title="t",
                create_time=1_700_000_000.0, update_time=1_700_000_000.0,
                messages=[
                    Message(role="user", text="你好嗎", time=1_700_000_000.0),     # 3 tok
                    Message(role="assistant", text="abcd", time=1_700_000_000.0),  # 1 tok
                ],
            ),
            Conversation(
                id="claude:y", platform="claude", title="t2",
                create_time=1_700_000_000.0, update_time=1_700_000_000.0,
                messages=[
                    Message(role="user", text="安安", time=1_700_000_000.0),       # 2 tok
                    Message(role="assistant", text="okok", time=1_700_000_000.0),  # 1 tok (ceil(4/4))
                ],
            ),
        ]
        store.build(convs, db)
        dist = store.distribution(db)
        # 兩段對話同平台同月 → 應彙總成一列，n=2（對話數，非訊息數）。
        assert len(dist) == 1, dist
        row = dist[0]
        assert row["platform"] == "claude", row
        assert row["n"] == 2, row              # 2 段對話（不是 4 則訊息）
        assert row["tokens"] == 7, row         # (3+1) + (2+1) = 7
    print("OK: all assertions passed")


if __name__ == "__main__":
    main()
