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
    print("OK: all assertions passed")


if __name__ == "__main__":
    main()
