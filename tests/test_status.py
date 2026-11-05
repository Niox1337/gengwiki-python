from gengwiki import AuthError, GengWiki, UnavailableError
from tests.fake import KEY_A, KEY_B
from tests.test_memes import Base


class StatusTest(Base):
    def test_counts_what_the_key_was_given(self):
        s = self.client().status()
        self.assertEqual((s.persona, s.memes, s.people, s.missing, s.stale), ("毒舌老哥", 2, 1, [], False))
        self.assertGreater(s.stickers, 0)
        self.assertGreater(s.quotes, 0)
        self.assertEqual((self.client(KEY_B).status().stickers, self.client(KEY_B).status().people), (0, 0))

    def test_a_missing_scope_is_named_and_the_rest_still_counts(self):
        self.fake.keys[KEY_A]["scopes"] = ["memes:read"]
        s = self.client().status()
        self.assertEqual(s.missing, ["persona:read", "stickers:read", "people:read", "trending:read"])
        self.assertEqual((s.persona, s.memes, s.stickers, s.people, s.quotes), ("", 2, 0, 0, 0))

    def test_a_bad_key_or_a_wiki_out_of_reach_raises(self):
        with self.assertRaises(AuthError):
            self.client("gwk_live_nope").status()
        self.fake.status = 500
        with self.assertRaises(UnavailableError):
            self.client().status()

    def test_an_outage_answers_from_the_old_copy_and_says_so(self):
        c = self.client()
        c.status()
        c.refresh()
        self.fake.status = 500
        self.assertTrue(c.status().stale)
