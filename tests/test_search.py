import unittest

from gengwiki._search import match_memes, search_entries, search_memes, search_stickers, similarity


def row(title, aliases=(), heat=0):
    return {"slug": title, "title": title, "aliases": list(aliases), "heat": heat}


class SearchTest(unittest.TestCase):
    def test_scenario_is_searched_but_does_not_outrank_a_name(self):
        rows = [row("牛马", heat=1) | {"usage_scenario": "加班到深夜时"}, row("加班狗", heat=0)]
        self.assertEqual([r["title"] for r in search_memes("加班", rows, 5)], ["加班狗", "牛马"])

    def test_match_finds_names_written_in_the_text(self):
        rows = [row("躺平", ["摆烂"], heat=1), row("YYDS", heat=9), row("班味", ["班"], heat=5)]
        self.assertEqual([r["title"] for r in match_memes("今天彻底摆烂了，yyds", rows, 5)], ["YYDS", "躺平"])
        self.assertEqual(match_memes("上班好累", rows, 5), [])  # the one character alias does not count

    def test_similarity_matches_pg_trgm(self):
        # select similarity('word', 'two words') is 0.363636 in Postgres.
        self.assertAlmostEqual(similarity("word", "two words"), 4 / 11)
        self.assertEqual(similarity("", "x"), 0)

    def test_substring_is_case_insensitive_and_literal(self):
        rows = [row("YYDS", ["永远的神"]), row("100%真实")]
        self.assertEqual([r["title"] for r in search_memes("yyds", rows, 5)], ["YYDS"])
        self.assertEqual([r["title"] for r in search_memes("永远", rows, 5)], ["YYDS"])
        self.assertEqual([r["title"] for r in search_memes("0%", rows, 5)], ["100%真实"])
        self.assertEqual(search_memes("不存在的词", rows, 5), [])

    def test_order_is_similarity_then_heat(self):
        rows = [row("躺平青年", heat=99), row("躺平", heat=1), row("躺平", heat=5)]
        self.assertEqual([r["heat"] for r in search_memes("躺平", rows, 5)], [5, 1, 99])

    def test_empty_query_keeps_server_order_and_limit(self):
        rows = [row("a", heat=2), row("b", heat=1)]
        self.assertEqual(search_memes(" ", rows, 1), rows[:1])

    def test_stickers_match_pack_fields(self):
        packs = [{"id": "p", "title": "猫猫", "tags": ["可爱"], "stickers": [{"id": "s", "caption": "震惊", "url": "u"}]}]
        for q in ("震惊", "猫", "可爱"):
            self.assertEqual(search_stickers(q, packs, 5)[0]["pack_id"], "p")
        self.assertEqual(search_stickers("狗", packs, 5), [])

    def test_a_sticker_asked_for_by_caption_beats_the_rest_of_its_matches(self):
        def sticker(caption):
            return {"id": caption, "caption": caption, "url": "u"}

        packs = [
            {"id": "a", "title": "笑", "tags": [], "stickers": [sticker("哭")]},
            {"id": "b", "title": "猫", "tags": [], "stickers": [sticker("笑哭"), sticker("笑"), sticker("大笑\n不止")]},
        ]
        self.assertEqual([s["id"] for s in search_stickers("笑", packs, 5)], ["笑", "笑哭", "大笑\n不止", "哭"])
        self.assertEqual(search_stickers(" 大笑  不止 ", packs, 1)[0]["id"], "大笑\n不止")
        self.assertEqual([s["id"] for s in search_stickers("", packs, 5)], ["哭", "笑哭", "笑", "大笑\n不止"])

    def test_entries(self):
        e = [{"term": "摆烂", "aliases": ["bailan"], "note": "", "tags": []}]
        self.assertEqual(search_entries("BAILAN", e, 5), e)


if __name__ == "__main__":
    unittest.main()
