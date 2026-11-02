import tempfile
import time
import unittest

from gengwiki import AuthError, GengWiki, NotFoundError, RateLimitError, ServerError
from tests.fake import KEY_A, KEY_B, Fake, meme, serve


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
        c.refresh()
        for status in (500, 429):
            self.fake.status = status
            before = c.request_count
            started = time.monotonic()
            self.assertEqual(c.search_memes("躺平")[0].slug, "tang-ping")
            self.assertEqual(c.request_count, before + 1)
            self.assertLess(time.monotonic() - started, 0.4)

    def test_outage_without_a_copy_raises(self):
        self.fake.status = 500
        with self.assertRaises(ServerError):
            self.client().search_memes()
        self.fake.status = 429
        with self.assertRaises(RateLimitError) as e:
            self.client().search_memes()
        self.assertEqual(e.exception.retry_after, 3600)

    def test_revoked_key_gets_an_auth_error_not_stale_data(self):
        c = self.client()
        c.search_memes()
        c.refresh()
        self.fake.keys[KEY_A]["revoked"] = True
        with self.assertRaises(AuthError):
            c.search_memes()

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


if __name__ == "__main__":
    unittest.main()
