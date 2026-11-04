import tempfile
import time
import unittest
from unittest import mock

from gengwiki import AuthError, BadResponseError, GengWiki, NotFoundError, RateLimitError, ServerError
from gengwiki.client import OUTAGE_PAUSE
from tests.fake import KEY_A, KEY_B, SUMMARY, Fake, meme, serve


class Base(unittest.TestCase):
    def setUp(self):
        self.fake = Fake()
        self.url, stop = serve(self.fake)
        self.addCleanup(stop)
        self.dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.dir.cleanup)

    def client(self, key=KEY_A, **kwargs):
        c = GengWiki(key, base_url=self.url, site_url=self.url, home=self.dir.name, **kwargs)
        self.addCleanup(c.close)
        return c


class MemeTest(Base):
    def test_meme_prompt_puts_named_memes_first_and_takes_no_extra_requests(self):
        c = self.client()
        prompt = c.meme_prompt("YYDS 了", limit=2)
        lines = [l for l in prompt.splitlines() if l.startswith("- ")]
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("- YYDS（永远的神）：YYDS的释义 使用场景：YYDS的场景"))
        sent = c.request_count
        c.meme_prompt("躺平")
        self.assertEqual([m.slug for m in c.match_memes("摆烂中")], ["tang-ping"])
        self.assertEqual(c.request_count, sent)

    def test_meme_prompt_survives_a_missing_scope_and_an_empty_scope(self):
        self.fake.keys[KEY_A]["scopes"] = ["memes:read"]
        c = self.client()
        self.assertIn("躺平", c.meme_prompt())
        self.fake.keys[KEY_A]["scopes"] = ["persona:read"]
        c.refresh()
        self.assertEqual(c.meme_prompt(), "")

    def test_many_searches_cost_one_request(self):
        c = self.client()
        self.assertEqual([m.slug for m in c.search_memes("躺平")], ["tang-ping"])
        self.assertEqual([m.slug for m in c.search_memes("永远的神")], ["yyds"])
        self.assertEqual(c.search_memes("完全不存在"), [])
        self.assertEqual([m.slug for m in c.search_memes()], ["tang-ping", "yyds"])
        self.assertEqual(c.request_count, 1)

    def test_a_new_process_needs_no_requests(self):
        self.client().search_memes("躺平")
        c = self.client()
        self.assertEqual(c.search_memes("躺平")[0].title, "躺平")
        self.assertEqual(c.request_count, 0)

    def test_detail_is_cached_and_found_by_alias(self):
        c = self.client()
        self.assertEqual(c.meme("tang-ping").body, "躺平的正文")
        self.assertEqual(c.meme("摆烂").slug, "tang-ping")
        self.assertEqual(self.fake.count("/v1/memes/tang-ping"), 1)
        self.assertEqual(c.request_count, 2)

    def test_edited_meme_is_refetched_after_the_list_refreshes(self):
        c = self.client()
        c.meme("yyds")
        self.fake.memes["yyds"] = meme("yyds", "新标题", 5, updated_at="2026-02-02T00:00:00Z")
        c.refresh()
        self.assertEqual(c.meme("yyds").title, "新标题")

    def test_unchanged_meme_survives_a_refresh(self):
        c = self.client()
        c.meme("yyds")
        c.refresh()
        c.meme("yyds")
        self.assertEqual(self.fake.count("/v1/memes/yyds"), 1)

    def test_out_of_scope_slug_needs_no_request_and_shared_copy_does_not_leak(self):
        self.client(KEY_A).meme("tang-ping")  # now in the shared cache
        c = self.client(KEY_B)
        with self.assertRaises(NotFoundError):
            c.meme("tang-ping")
        self.assertEqual(self.fake.count("/v1/memes/tang-ping"), 1)
        self.assertEqual(c.request_count, 1)  # only KEY_B's own list

    def test_second_key_reuses_the_text(self):
        self.client(KEY_A).meme("yyds")
        c = self.client(KEY_B)
        self.assertEqual(c.meme("yyds").body, "YYDS的正文")
        self.assertEqual(self.fake.count("/v1/memes/yyds"), 1)

    def test_truncated_list_falls_back_to_server(self):
        for i in range(120):
            m = meme(f"m{i}", f"梗{i}", heat=1000 - i)
            self.fake.memes[m["slug"]] = m
            self.fake.keys[KEY_A]["memes"].append(m["slug"])
        c = self.client()
        self.assertEqual(c.search_memes("梗119")[0].slug, "m119")  # past the first 100 by heat
        c.search_memes("梗119")
        self.assertEqual(c.request_count, 2)
        self.assertEqual(c.meme("m119").slug, "m119")
        c.meme("m119")
        self.assertEqual(self.fake.count("/v1/memes/m119"), 1)
        with self.assertRaises(NotFoundError):
            c.meme("nope")
        with self.assertRaises(NotFoundError):
            c.meme("nope")
        self.assertEqual(self.fake.count("/v1/memes/nope"), 1)  # a miss is remembered too

    def test_trending_serves_any_limit_and_all_keys_from_one_request(self):
        c = self.client()
        self.assertEqual(len(c.trending(limit=1)), 1)
        self.assertEqual(len(c.trending(limit=2)), 2)
        self.assertEqual(self.client(KEY_B).trending()[0].slug, "tang-ping")
        self.assertEqual(self.fake.count("/v1/trending"), 1)

    def test_outage_serves_stale_copy_without_retrying(self):
        c = self.client()
        c.search_memes()
        for status in (500, 429):
            c.refresh()
            self.fake.status = status
            before = c.request_count
            started = time.monotonic()
            self.assertEqual(c.search_memes("躺平")[0].slug, "tang-ping")
            self.assertEqual(c.request_count, before + 1)
            self.assertLess(time.monotonic() - started, 0.4)
            self.assertTrue(c.stale)
        self.fake.status = None
        c.refresh()
        self.assertFalse(c.stale)
        c.search_memes()
        self.assertFalse(c.stale)

    def test_outage_without_a_copy_raises(self):
        self.fake.status = 500
        with self.assertRaises(ServerError):
            self.client().search_memes()
        self.fake.status = 429
        with self.assertRaises(RateLimitError) as e:
            self.client().search_memes()
        self.assertEqual(e.exception.retry_after, 3600)

    def test_html_with_a_200_serves_the_stale_copy(self):
        c = self.client()
        c.search_memes()
        c.refresh()
        self.fake.html_ok = True
        self.assertEqual(c.search_memes("躺平")[0].slug, "tang-ping")

    def test_html_with_a_200_and_no_copy_raises_and_is_not_cached(self):
        self.fake.html_ok = True
        c = self.client()
        with self.assertRaisesRegex(BadResponseError, "text/html"):
            c.search_memes()
        self.fake.html_ok = False
        self.assertEqual(c.search_memes("躺平")[0].slug, "tang-ping")

    def test_revoked_key_gets_an_auth_error_not_stale_data(self):
        c = self.client()
        c.search_memes()
        c.refresh()
        self.fake.keys[KEY_A]["revoked"] = True
        with self.assertRaises(AuthError):
            c.search_memes()

    def test_base_url_may_include_v1(self):
        c = GengWiki(KEY_A, base_url=self.url + "/v1/", site_url=self.url, home=self.dir.name)
        self.addCleanup(c.close)
        self.assertEqual(c.base_url, self.url)
        self.assertEqual(c.search_memes()[0].slug, "tang-ping")

    def test_default_address_is_production(self):
        c = GengWiki(home=self.dir.name)
        self.addCleanup(c.close)
        self.assertEqual(c.base_url, "https://api.gengwiki.niox.lol")

    def test_no_key_says_how_to_get_one(self):
        c = GengWiki(base_url=self.url, site_url=self.url, home=self.dir.name)
        self.addCleanup(c.close)
        with self.assertRaisesRegex(AuthError, "GENGWIKI_API_KEY"):
            c.search_memes()
        self.assertEqual(c.request_count, 0)

    def test_the_key_never_reaches_the_cache_file(self):
        c = self.client()
        c.search_memes()
        c.close()
        for f in c.home.iterdir():
            self.assertNotIn(KEY_A.encode(), f.read_bytes(), f.name)

    def test_scenario_on_lists_detail_and_related(self):
        self.fake.memes["tang-ping"]["related"] = [{"slug": "yyds", "usage_scenario": "夸人时"}]
        c = self.client()
        self.assertEqual(c.search_memes("躺平")[0].usage_scenario, "躺平的场景")
        self.assertEqual(c.trending()[0].usage_scenario, "躺平的场景")
        self.assertEqual(c.meme("tang-ping").usage_scenario, "躺平的场景")
        self.assertEqual(c.meme("tang-ping").related[0].usage_scenario, "夸人时")

    def test_a_server_without_scenario_still_works(self):
        older = tuple(f for f in SUMMARY if f != "usage_scenario")
        with mock.patch("tests.fake.SUMMARY", older):
            self.assertEqual(self.client().search_memes("躺平")[0].usage_scenario, "")

    def test_wrong_json_is_not_kept(self):
        c = self.client()
        self.fake.json_ok = {"message": "ok"}
        with self.assertRaises(BadResponseError):
            c.search_memes("躺平")
        self.fake.json_ok = None
        self.assertEqual(c.search_memes("躺平")[0].slug, "tang-ping")

    def test_wrong_json_serves_the_stale_copy(self):
        c = self.client()
        c.search_memes()
        c.refresh()
        self.fake.json_ok = {"message": "ok"}
        self.assertEqual(c.search_memes("躺平")[0].slug, "tang-ping")

    def test_wrong_json_type_for_a_persona(self):
        self.fake.json_ok = ["not", "a", "persona"]
        with self.assertRaises(BadResponseError):
            self.client().persona()

    def test_outage_asks_once_then_waits(self):
        c = self.client()
        c.search_memes()
        c.refresh()
        self.fake.status = 500
        for _ in range(5):
            c.search_memes("躺平")
        self.assertEqual(self.fake.count("/v1/memes/search"), 2)  # the first read, and one failed refresh
        later = time.time() + OUTAGE_PAUSE + 1
        with mock.patch("time.time", return_value=later):
            c.search_memes("躺平")
        self.assertEqual(self.fake.count("/v1/memes/search"), 3)

    def test_rate_limit_waits_for_the_whole_retry_after(self):
        c = self.client()
        c.search_memes()
        c.refresh()
        self.fake.status = 429  # the fake says Retry-After 3600
        c.search_memes("躺平")
        with mock.patch("time.time", return_value=time.time() + 3000):
            c.search_memes("躺平")
        self.assertEqual(self.fake.count("/v1/memes/search"), 2)

    def test_a_limit_on_one_key_does_not_hold_back_another(self):
        c = self.client()
        c.search_memes()
        c.refresh()
        self.fake.status = 429
        c.search_memes("躺平")
        self.fake.status = None
        other = c.keys.add("b", KEY_B)
        c.keys.use(other.name)
        self.assertEqual([m.slug for m in c.search_memes("yyds")], ["yyds"])

    def test_refresh_ends_the_wait_and_a_recovery_is_seen(self):
        c = self.client()
        c.search_memes()
        c.refresh()
        self.fake.status = 500
        c.search_memes("躺平")
        self.fake.status = None
        self.fake.memes["tang-ping"]["title"] = "躺平二"
        c.refresh()
        self.assertEqual(c.search_memes("躺平")[0].title, "躺平二")


if __name__ == "__main__":
    unittest.main()
