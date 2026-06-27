"""clean_text / _unwrap_token 的單元測試（純 stdlib unittest，零依賴）。

涵蓋 ChatGPT 內嵌 token 的解包（保留顯示文字）與移除（純 metadata），
以及 Grok 標籤清理的回歸。執行：

    python -m unittest tests.test_clean_text -v
"""

import unittest

from ai_archive.parsers._util import clean_text, _unwrap_token

E200, E201, E202 = "", "", ""


def tok(*segs: str) -> str:
    """組一個 U+E200..E201 內嵌 token，segments 以 U+E202 分隔。"""
    return E200 + E202.join(segs) + E201


class UnwrapToken(unittest.TestCase):
    def test_url_becomes_markdown_link(self):
        body = E202.join(["url", "BUFFALO", "https://www.buffalo.jp/"])
        self.assertEqual(_unwrap_token(body), "[BUFFALO](https://www.buffalo.jp/)")

    def test_entity_keeps_display_name(self):
        body = E202.join(["entity", '["other","MBTI","personality framework"]'])
        self.assertEqual(_unwrap_token(body), "MBTI")

    def test_product_keeps_name_at_index_1(self):
        body = E202.join(
            ["product", '["turn0product1","PAIR ACNE Cream W",{"render_as":"hero"}]'])
        self.assertEqual(_unwrap_token(body), "PAIR ACNE Cream W")

    def test_brand_and_medication_keep_name(self):
        self.assertEqual(
            _unwrap_token(E202.join(["brand", '["brand","Curel","skincare"]'])), "Curel")
        self.assertEqual(
            _unwrap_token(E202.join(["medication", '["medication","Tretinoin","A酸"]'])),
            "Tretinoin")

    def test_video_and_navlist_keep_title(self):
        self.assertEqual(
            _unwrap_token(E202.join(["video", "Night Sky Events", "turn0search3"])),
            "Night Sky Events")
        self.assertEqual(
            _unwrap_token(E202.join(["navlist", "相關報導", "turn0news20,turn0news21"])),
            "相關報導")

    def test_metadata_types_are_dropped(self):
        self.assertEqual(_unwrap_token(E202.join(["cite", "turn0search1"])), "")
        self.assertEqual(_unwrap_token(E202.join(["filecite", "turn0file0"])), "")
        self.assertEqual(
            _unwrap_token(E202.join(["image_group", '{"query":["a","b"]}'])), "")
        self.assertEqual(_unwrap_token(E202.join(["i", "turn0image0"])), "")
        self.assertEqual(_unwrap_token("map"), "")

    def test_entity_metadata_is_dropped_not_kept(self):
        # [1] 是版面提示 "one-line" 而非名稱，必須被丟棄
        body = E202.join(
            ["entity_metadata", '["turn0business3","one-line","Yakiniku Ponga"]'])
        self.assertEqual(_unwrap_token(body), "")

    def test_unknown_type_and_bad_json_drop_safely(self):
        self.assertEqual(_unwrap_token(E202.join(["totally_new_type", "x"])), "")
        self.assertEqual(_unwrap_token(E202.join(["entity", "not-json"])), "")


class CleanTextIntegration(unittest.TestCase):
    def test_inline_link_text_survives(self):
        # 先前的「缺字」案例：url 顯示文字只存在 token 內
        raw = "保存計畫：\n\n" + tok(
            "url", "Flashpoint Archive", "https://flashpointarchive.org") + "\n\n目標"
        out = clean_text(raw)
        self.assertIn("Flashpoint Archive", out)
        self.assertIn("(https://flashpointarchive.org)", out)

    def test_entity_subject_survives_in_sentence(self):
        raw = "2010 年。" + tok(
            "entity", '["known_celebrity","Steve Jobs","Apple co-founder"]') + " 發表文章"
        self.assertIn("Steve Jobs", clean_text(raw))

    def test_no_pua_residue(self):
        raw = ("文字" + tok("cite", "turn0search1")
               + tok("image_group", '{"query":["x"]}') + "結尾")
        out = clean_text(raw)
        self.assertFalse(any(0xE000 <= ord(ch) <= 0xF8FF for ch in out),
                         "輸出不應殘留任何私有區字元")

    def test_grok_render_still_stripped(self):
        raw = '答案<grok:render type="citation">[1]</grok:render>很明確'
        self.assertEqual(clean_text(raw), "答案很明確")

    def test_empty_and_plain_text_passthrough(self):
        self.assertEqual(clean_text(""), "")
        self.assertEqual(clean_text("一般文字 no tokens"), "一般文字 no tokens")


if __name__ == "__main__":
    unittest.main()
