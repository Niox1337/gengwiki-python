import unittest

from gengwiki import ForbiddenError
from tests.fake import KEY_A
from tests.test_memes import Base


class LexiconTest(Base):
    def test_writes_update_the_cache_without_a_reread(self):
        c = self.client()
        self.assertEqual(c.lexicons(), [])
        lex = c.create_lexicon("我的词库", "说明")
        self.assertEqual(c.lexicons()[0].name, "我的词库")
        self.assertEqual(c.lexicon_entries(lex.id), [])
        e = c.add_lexicon_entry(lex.id, "摆烂", aliases=["bailan"], note="不想努力了")
        self.assertEqual(c.lexicon_entries(lex.id), [e])
        self.assertEqual(c.lexicons()[0].entries, 1)
        self.assertEqual(c.search_lexicons("BAILAN"), [e])
        self.assertEqual(c.search_lexicons("没有"), [])
        self.assertEqual(self.fake.count("/v1/me/lexicons"), 4)  # 2 reads, 2 writes

    def test_write_without_scope_raises(self):
        self.fake.keys[KEY_A]["scopes"] = ["lexicon:read:self"]
        with self.assertRaises(ForbiddenError):
            self.client().create_lexicon("x")


class UsageTest(Base):
    def test_always_live(self):
        c = self.client()
        self.assertEqual(c.rate_limit().per_minute, 600)
        c.rate_limit()
        self.assertEqual(c.usage()["days"][0]["requests"], 3)
        self.assertEqual(c.request_count, 3)


if __name__ == "__main__":
    unittest.main()
