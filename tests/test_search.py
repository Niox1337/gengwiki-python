import unittest

from gengwiki._search import search_entries, search_memes, search_stickers, similarity


def row(title, aliases=(), heat=0):
    return {"slug": title, "title": title, "aliases": list(aliases), "heat": heat}


class SearchTest(unittest.TestCase):
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

    def test_entries(self):
        e = [{"term": "摆烂", "aliases": ["bailan"], "note": "", "tags": []}]
        self.assertEqual(search_entries("BAILAN", e, 5), e)


if __name__ == "__main__":
    unittest.main()
