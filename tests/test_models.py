import unittest

from gengwiki.models import Meme, StickerPack


class ModelTest(unittest.TestCase):
    def test_unknown_fields_are_dropped_and_nested_are_built(self):
        m = Meme.of({"slug": "a", "future": 1, "related": [{"slug": "b", "future": 2}], "contributors": [{"name": "c"}]})
        self.assertEqual((m.slug, m.related[0].slug, m.contributors[0].name), ("a", "b", "c"))
        self.assertEqual(m.to_dict()["related"][0]["slug"], "b")

    def test_stickers_know_their_pack(self):
        p = StickerPack.of({"id": "p", "title": "猫猫", "stickers": [{"id": "s"}]})
        self.assertEqual(p.stickers[0].pack_title, "猫猫")


if __name__ == "__main__":
    unittest.main()
