from unittest import mock

from tests.fake import LU_XUN, meme
from tests.test_memes import Base


class SemanticTest(Base):
    def setUp(self):
        super().setUp()
        # More memes than a turn shows, so only the ranking can explain a meme being there every time.
        for i in range(40):
            m = meme(f"m{i}", f"梗{i}", heat=1)
            self.fake.memes[m["slug"]] = m
        self.fake.keys[next(iter(self.fake.keys))]["memes"] = list(self.fake.memes)

    def memes_in(self, prompt):
        block = prompt.split("<memes>")[1].split("</memes>")[0]
        return [line for line in block.splitlines() if line.startswith("- ")]

    def test_off_by_default(self):
        c = self.client(meme_frequency=1)
        c.turn("今天好累")
        self.assertEqual(self.fake.count("/v1/relevant"), 0)

    def test_ranked_memes_reach_the_prompt_after_the_named_ones(self):
        self.fake.relevant = {"memes": ["m37", "m38"]}
        c = self.client(meme_frequency=1, semantic=True)
        for _ in range(5):
            lines = self.memes_in(c.turn("YYDS 今天又加班").prompt)
            self.assertEqual(len(lines), 15)
            self.assertTrue(lines[0].startswith("- YYDS"))
            self.assertTrue(lines[1].startswith("- 梗37"))
            self.assertTrue(lines[2].startswith("- 梗38"))
        body = self.fake.relevant_bodies[0]
        self.assertEqual(body["text"], "YYDS 今天又加班")
        self.assertIn("m37", body["memes"])
        self.assertFalse(body["quotes"])

    def test_semantic_false_falls_back_and_pauses(self):
        c = self.client(meme_frequency=1, semantic=True)
        first, second = c.turn("今天好累"), c.turn("还是好累")
        self.assertEqual(len(self.memes_in(first.prompt)), 15)
        self.assertEqual(len(self.memes_in(second.prompt)), 15)
        self.assertEqual(self.fake.count("/v1/relevant"), 1)

    def test_an_error_falls_back_and_pauses(self):
        self.fake.relevant = 500
        c = self.client(meme_frequency=1, semantic=True)
        self.assertEqual(len(self.memes_in(c.turn("今天好累").prompt)), 15)
        c.turn("还是好累")
        self.assertEqual(self.fake.count("/v1/relevant"), 1)
        with mock.patch("time.time", return_value=c._semantic_paused + 1):
            c.turn("又一次")
        self.assertEqual(self.fake.count("/v1/relevant"), 2)

    def test_no_request_without_a_key_or_text_or_a_roll(self):
        self.fake.relevant = {"memes": ["m1"]}
        self.client(key=None, meme_frequency=1, semantic=True).turn("今天好累")
        c = self.client(meme_frequency=1, semantic=True)
        c.turn("")
        c.turn("   ")
        self.client(meme_frequency=0, quote_frequency=0, semantic=True).turn("今天好累")
        self.assertEqual(self.fake.count("/v1/relevant"), 0)

    def test_ranked_quotes_lead_the_quote_list(self):
        self.fake.people[LU_XUN]["quotes"] = [f"语录{i}" for i in range(12)]
        self.fake.relevant = {"quotes": [{"person": "鲁迅", "text": "语录11"}, {"person": "鲁迅", "text": "语录10"}]}
        c = self.client(meme_frequency=0, quote_frequency=0.5, semantic=True)
        with mock.patch("random.random", return_value=0.1):
            prompt = c.turn("随便聊聊").prompt
        rows = [r for r in prompt.split("<quotes>")[1].split("</quotes>")[0].splitlines() if r.startswith("- ")]
        self.assertEqual(rows[:2], ["- 鲁迅 语录11", "- 鲁迅 语录10"])
        self.assertEqual(len(rows), 6)
        self.assertTrue(self.fake.relevant_bodies[0]["quotes"])
        self.assertEqual(self.fake.relevant_bodies[0]["memes"], [])
