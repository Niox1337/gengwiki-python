import json
import unittest
from unittest import mock

from gengwiki import ForbiddenError, NotFoundError, UnavailableError
from tests.fake import KEY_A, KEY_B, meme
from tests.test_memes import Base


class SubscriptionTest(Base):
    def setUp(self):
        super().setUp()
        # A full hot board, so nothing with this tag gets in except through a subscription
        for i in range(100):
            self.fake.memes[f"hot-{i}"] = meme(f"hot-{i}", f"热{i}", 100 + i)
        for i in range(1, 7):
            m = meme(f"game-{i}", f"游戏{i}", 10 - i)
            m["categories"] = ["游戏"]
            self.fake.memes[m["slug"]] = m

    def lines(self, prompt):
        return [l for l in prompt.splitlines() if l.startswith("- ")]

    def test_tags_lists_every_tag_once_for_all_keys(self):
        c = self.client()
        self.assertEqual([(t.name, t.count) for t in c.tags()], [("网络", 102), ("游戏", 6)])
        self.client(KEY_B).tags()
        self.assertEqual(self.fake.count("/v1/tags"), 1)
        self.fake.keys[KEY_A]["scopes"] = ["memes:read"]
        c.refresh()
        with self.assertRaises(ForbiddenError):
            c.tags()

    def age(self, c, seconds):
        c._store._run("update cache_v1 set fetched_at = fetched_at - ?", (seconds,))

    def tag(self, slug, title, tag):
        m = meme(slug, title, 1)
        m["categories"] = [tag]
        self.fake.memes[slug] = m

    def test_a_new_tag_shows_up_within_a_quarter_hour(self):
        c = self.client()
        c.tags()
        self.tag("new-1", "新梗", "新标签")
        self.assertNotIn("新标签", [t.name for t in c.tags()])
        self.age(c, 15 * 60 + 1)
        self.assertIn("新标签", [t.name for t in c.tags()])

    def test_an_empty_board_checks_again_within_a_minute(self):
        c = self.client()
        with self.assertRaises(NotFoundError):
            c.subscribe("新标签")
        sent = self.fake.count("/v1/trending")
        with self.assertRaises(NotFoundError):
            c.subscribe("新标签")
        self.assertEqual(self.fake.count("/v1/trending"), sent, "a miss is still cached for a moment")
        self.tag("new-1", "新梗", "新标签")
        self.age(c, 61)
        self.assertEqual([m.slug for m in c.subscribe("新标签")], ["new-1"])
        # A board with memes keeps its full time
        self.age(c, 61)
        sent = self.fake.count("/v1/trending")
        c.subscribe("新标签")
        self.assertEqual(self.fake.count("/v1/trending"), sent)

    def test_a_tag_with_fewer_than_five(self):
        self.tag("few-1", "冷门1", "冷门")
        self.tag("few-2", "冷门2", "冷门")
        c = self.client()
        self.assertEqual(len(c.subscribe("冷门")), 2)
        for limit in (1, 2, 3, 15):
            lines = self.lines(c.meme_prompt(limit=limit))
            self.assertEqual(len(lines), limit)
            self.assertEqual(len(lines), len(set(lines)))
        self.assertEqual(sum("冷门" in l for l in self.lines(c.meme_prompt(limit=15))), 2)

    def test_a_tag_that_lost_its_memes_stays_harmless(self):
        c = self.client()
        c.subscribe("游戏")
        for i in range(1, 7):
            del self.fake.memes[f"game-{i}"]
        c.refresh()
        self.assertEqual(c.subscriptions(), ["游戏"])
        self.assertEqual(len(self.lines(c.meme_prompt(limit=15))), 15)
        self.assertTrue(c.unsubscribe("游戏"))

    def test_any_iterable_of_tags_gets_the_places(self):
        c = self.client()
        lines = self.lines(c.meme_prompt(limit=4, tags=(t for t in ["游戏"])))
        self.assertGreaterEqual(sum("游戏" in l for l in lines), 2)

    def test_an_outage_on_a_tag_never_read_keeps_the_rest(self):
        c = self.client()
        c.meme_prompt()
        self.fake.status = 500
        self.assertEqual(c.match_memes("躺平", tags=["没读过"])[0].slug, "tang-ping")
        self.assertIn("躺平", c.meme_prompt(limit=100, tags=["没读过"]))
        with self.assertRaises(UnavailableError):
            c.trending("没读过")

    def test_switching_persona_keeps_the_subscription(self):
        c = self.client()
        c.keys.add("老哥", KEY_A)
        c.keys.add("姐姐", KEY_B)
        c.keys.use("老哥")
        self.fake.memes["yyds"]["categories"] = ["游戏"]
        self.fake.memes["yyds"]["heat"] = 50  # bound to 姐姐 only, and top of the tag
        self.fake.keys[KEY_A]["memes"] = ["tang-ping"]
        c.subscribe("游戏")
        c.meme_prompt()
        self.assertEqual(c.use_persona("温柔姐姐").title, "温柔姐姐")
        sent = self.fake.count("/v1/trending")
        self.assertEqual(c.subscriptions(), ["游戏"])
        slugs = [r["slug"] for r in c._pool()]
        self.assertEqual(len(slugs), len(set(slugs)))
        self.assertIn("game-1", slugs)
        self.assertNotIn("tang-ping", slugs, "the other persona's bound meme went with its key")
        for _ in range(10):
            lines = self.lines(c.meme_prompt(limit=15))
            self.assertEqual(len(lines), len(set(lines)))
        self.assertEqual(self.fake.count("/v1/trending"), sent, "the boards are shared between keys")

    def test_find_covers_the_tags_and_the_hot_board(self):
        c = self.client()
        self.assertEqual(c.search_memes("游戏1"), [])
        self.assertEqual(c.find_memes("游戏1"), [])
        c.subscribe("游戏")
        self.assertEqual(c.find_memes("游戏1")[0].slug, "game-1")
        self.assertEqual(c.find_memes("热5")[0].slug, "hot-5")
        self.assertEqual(c.find_memes("躺平")[0].slug, "tang-ping")
        self.assertEqual(c.search_memes("游戏1"), [], "this one stays with the key's own")
        self.assertNotIn("game-6", [m.slug for m in c.find_memes("游戏6", limit=100)], "only the top five")
        self.assertEqual(c.find_memes("游戏1", tags=[]), [])
        c.unsubscribe("游戏")
        self.assertEqual(c.find_memes("游戏1", tags=["游戏"])[0].slug, "game-1")

    def test_find_lists_each_meme_once_and_reaches_past_a_cut_off_list(self):
        self.fake.memes["tang-ping"]["categories"] = ["游戏"]
        self.fake.memes["tang-ping"]["heat"] = 50
        c = self.client()
        c.subscribe("游戏")
        self.assertEqual(sum(m.slug == "tang-ping" for m in c.find_memes(limit=100)), 1)
        self.fake.memes["far"] = meme("far", "很远的梗", 0)
        self.fake.keys[KEY_A]["memes"] = [f"hot-{i}" for i in range(100)] + ["far"]
        c.refresh()
        self.assertEqual(c.find_memes("很远的梗")[0].slug, "far")

    def test_find_without_the_scopes(self):
        c = self.client()
        self.fake.keys[KEY_A]["scopes"] = ["trending:read"]
        self.assertEqual(c.find_memes("热5")[0].slug, "hot-5")
        self.fake.keys[KEY_A]["scopes"] = ["memes:read"]
        c.refresh()
        self.assertEqual(c.find_memes("躺平")[0].slug, "tang-ping")

    def test_an_outage_on_the_hot_board_keeps_the_key_s_memes(self):
        c = self.client()
        c.search_memes()
        self.fake.status = 500
        self.assertEqual(c.find_memes("躺平")[0].slug, "tang-ping")

    def test_the_tools_find_them_and_get_meme_answers_with_the_summary(self):
        c = self.client()
        c.subscribe("游戏")
        found = json.loads(c.tools.call("search_memes", {"q": "游戏1"}))
        self.assertEqual(found[0]["slug"], "game-1")
        got = json.loads(c.tools.call("get_meme", {"slug": found[0]["slug"]}))
        self.assertEqual((got["summary"], got["usage_scenario"]), ("游戏1的释义", "游戏1的场景"))
        self.assertIn("note", got)
        self.assertNotIn("body", got)
        self.assertIn("note", json.loads(c.tools.call("get_meme", {"slug": "游戏1"})))
        self.assertIn("body", json.loads(c.tools.call("get_meme", {"slug": "tang-ping"})))
        self.assertEqual(json.loads(c.tools.call("get_meme", {"slug": "没有这个"}))["error"]["code"], "not_found")
        self.assertEqual(json.loads(c.tools.call("search_memes", {"q": "游戏1", "tags": []})), [])
        self.assertEqual(json.loads(c.tools.call("get_meme", {"slug": "game-1", "tags": []}))["error"]["code"], "not_found")

    def test_saved_for_every_key_and_later_clients(self):
        top = self.client().subscribe(" 游戏 ")
        self.assertEqual([m.slug for m in top], [f"game-{i}" for i in range(1, 6)])
        self.client().subscribe("游戏")
        self.assertEqual(self.client(KEY_B).subscriptions(), ["游戏"])
        self.assertTrue(self.client().unsubscribe("游戏"))
        self.assertFalse(self.client().unsubscribe("游戏"))
        self.assertEqual(self.client().subscriptions(), [])

    def test_unknown_tag_is_refused_and_not_saved(self):
        c = self.client()
        for tag in ("没有这个", "", "  "):
            with self.assertRaises(NotFoundError):
                c.subscribe(tag)
        self.assertEqual(c.subscriptions(), [])

    def test_only_the_top_five_reach_the_model(self):
        c = self.client()
        self.assertEqual(c.match_memes("游戏1"), [])
        c.subscribe("游戏")
        self.assertEqual(c.match_memes("游戏1")[0].slug, "game-1")
        self.assertEqual(c.match_memes("游戏6"), [])
        c.unsubscribe("游戏")
        self.assertEqual(c.match_memes("游戏1"), [])

    def test_they_get_places_next_to_the_hot_board(self):
        c = self.client()
        c.subscribe("游戏")
        lines = self.lines(c.meme_prompt(limit=4))
        self.assertEqual(len(lines), 4)
        self.assertGreaterEqual(sum("游戏" in l for l in lines), 2)  # at least, the random rest may bring another
        lines = self.lines(c.meme_prompt(limit=3))
        self.assertGreaterEqual(sum("游戏" in l for l in lines), 2)

    def test_a_bound_meme_is_not_repeated(self):
        self.fake.memes["tang-ping"]["categories"] = ["游戏"]
        self.fake.memes["tang-ping"]["heat"] = 50
        c = self.client()
        c.subscribe("游戏")
        for _ in range(20):
            prompt = c.meme_prompt(limit=15)
            self.assertLessEqual(prompt.count("- 躺平"), 1)
            slugs = self.lines(prompt)
            self.assertEqual(len(slugs), len(set(slugs)))
        self.assertEqual(sum(r["slug"] == "tang-ping" for r in c._pool()), 1)

    def test_tags_replace_the_saved_ones(self):
        c = self.client()
        c.subscribe("游戏")
        self.assertEqual(c.match_memes("游戏1", tags=[]), [])
        self.assertEqual(c.match_memes("游戏1", tags=["游戏"])[0].slug, "game-1")
        c.unsubscribe("游戏")
        self.assertEqual(c.match_memes("游戏1", tags=["游戏"])[0].slug, "game-1")
        self.assertGreaterEqual(sum("游戏" in l for l in self.lines(c.meme_prompt(limit=4, tags=["游戏"]))), 2)
        self.assertNotIn("游戏", c.meme_prompt(limit=4, tags=[]))
        with mock.patch("random.random", return_value=0.0):
            self.assertIn("游戏", c.turn("", tags=["游戏"]).prompt)

    def test_no_extra_requests_once_cached_and_boards_are_shared(self):
        c = self.client()
        c.subscribe("游戏")
        c.meme_prompt()
        self.assertEqual(self.fake.count("/v1/trending"), 2)
        sent = c.request_count
        c.meme_prompt()
        c.match_memes("游戏1")
        self.client(KEY_B).match_memes("游戏1")
        self.assertEqual(c.request_count, sent)
        self.assertEqual(self.fake.count("/v1/trending"), 2)

    def test_a_key_without_the_scope(self):
        c = self.client()
        c.subscribe("游戏")
        self.fake.keys[KEY_A]["scopes"] = ["memes:read"]
        c.refresh()
        self.assertIn("躺平", c.meme_prompt())
        self.assertEqual(c.match_memes("游戏1"), [])
        with self.assertRaises(ForbiddenError):
            c.subscribe("网络")

    def test_sync_takes_the_subscribed_boards_along(self):
        c = self.client()
        c.subscribe("游戏")
        c.refresh()
        c.sync()
        self.fake.status = 500
        self.assertEqual(c.match_memes("游戏1")[0].slug, "game-1")


if __name__ == "__main__":
    unittest.main()
