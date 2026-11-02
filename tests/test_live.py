"""The SDK against the real gengwiki services, to catch where tests/fake.py has drifted from them.

Skipped unless GENGWIKI_LIVE_API and GENGWIKI_LIVE_SITE point at a throwaway stack seeded with tests/live_seed.sql.
Never point it at production, it registers a user and creates keys.
"""

import json
import os
import tempfile
import unittest
import uuid

from gengwiki import AuthError, GengWiki, NotFoundError
from gengwiki._http import Http

API = os.environ.get("GENGWIKI_LIVE_API")
SITE = os.environ.get("GENGWIKI_LIVE_SITE")
PASSWORD = "sdk-live-password"
PACK = "33333333-3333-3333-3333-333333333333"
STICKER = "44444444-4444-4444-4444-444444444444"
ALL_SLUGS = ["tang-ping", "yyds", "ban-wei", "da-gong-ren", "50-percent", "under_score"]

# Exact, partial, fuzzy and literal-looking queries, each must rank the same here and on the server.
QUERIES = ["", "躺平", "躺", "摆烂", "躺平族", "班味", "上班", "上班味儿", "打工", "社畜", "yyds", "YYDS", "yy", "永远", "永远的神啊",
           "lie flat", "flat", "yong yuan", "yuan de", "50%", "%", "_", "snake_case", "Snake", "梗", "不存在的词", "  躺平  ", "a", "神"]


@unittest.skipUnless(API and SITE, "needs a throwaway gengwiki stack")
class LiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.email = f"{uuid.uuid4().hex}@example.com"
        Http().json("POST", f"{SITE}/api/auth/register", body={"email": cls.email, "password": PASSWORD, "invite": "sdk-live"})
        # Log in once, the backend allows ten logins a minute.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            c = GengWiki(base_url=API, site_url=SITE, home=d)
            c.keys.login(cls.email, PASSWORD)
            cls.session = c._keyring.read()["session"]
            c.close()

    def setUp(self):
        d = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(d.cleanup)
        self.c = self.client(d.name)
        with self.c._keyring.edit() as data:
            data["session"] = self.session

    def client(self, home):
        c = GengWiki(base_url=API, site_url=SITE, home=home)
        self.addCleanup(c.close)
        return c

    def key(self, name="all", **kwargs):
        k = self.c.keys.create(f"{name}-{uuid.uuid4().hex[:6]}", memes=ALL_SLUGS, packs=[PACK], **kwargs)
        self.c.keys.use(k.name)
        return k

    def test_local_search_ranks_exactly_like_the_server(self):
        self.key()
        self.c.search_memes()
        for q in QUERIES:
            server = self.c._http.json("GET", f"{API}/v1/memes/search", token=self.c._key, params={"q": q, "limit": 100})
            before = self.c.request_count
            local = self.c.search_memes(q, limit=100)
            self.assertEqual([m.slug for m in local], [m["slug"] for m in server], repr(q))
            self.assertEqual(self.c.request_count, before, "the list should already be cached")

    def test_local_sticker_search_matches_the_server(self):
        self.key()
        for q in ["", "震惊", "猫", "可爱", "动物", "开", "狗", "  猫 "]:
            server = self.c._http.json("GET", f"{API}/v1/stickers/search", token=self.c._key, params={"q": q})
            self.assertEqual([s.id for s in self.c.search_stickers(q)], [s["id"] for s in server], repr(q))
            for ours, theirs in zip(self.c.search_stickers(q), server):
                self.assertEqual((ours.caption, ours.url, ours.pack_id, ours.pack_title),
                                 (theirs["caption"], theirs["url"], theirs["pack"]["id"], theirs["pack"]["title"]))

    def test_catalog_search_matches_the_server(self):
        for q in ["老哥", "很软", "治愈", "搞笑", "没有", "说话"]:
            server = self.c._http.json("GET", f"{SITE}/api/personas", params={"q": q})
            self.assertEqual({p.id for p in self.c.personas(q)}, {p["id"] for p in server}, repr(q))

    def test_meme_detail_and_the_updated_at_shortcut(self):
        self.key()
        m = self.c.meme("摆烂")
        self.assertEqual((m.slug, m.body, m.usage_examples), ("tang-ping", "躺平的正文", ["我躺平了"]))
        self.assertEqual(m.related[0].slug, "da-gong-ren")
        self.assertEqual((m.usage_scenario, m.related[0].usage_scenario), ("加班后吐槽", "加班后吐槽"))
        self.assertEqual(self.c.search_memes("躺平")[0].usage_scenario, "加班后吐槽")
        self.assertEqual(self.c.trending()[0].usage_scenario, "加班后吐槽")
        before = self.c.request_count
        self.c.refresh()
        self.c.meme("tang-ping")  # the list is fetched again, its updated_at must equal the detail's
        self.assertEqual(self.c.request_count, before + 1)
        with self.assertRaises(NotFoundError):
            self.c.meme("not-a-meme")

    def test_scope_is_enforced(self):
        k = self.c.keys.create(f"small-{uuid.uuid4().hex[:6]}", memes=["yyds"])
        self.c.keys.use(k.name)
        self.assertEqual([m.slug for m in self.c.search_memes()], ["yyds"])
        with self.assertRaises(NotFoundError):
            self.c.meme("tang-ping")
        self.assertEqual(len(self.c.trending(limit=100)), 6)  # the board ignores the scope

    def test_switching_personas_creates_then_reuses_keys(self):
        p = self.c.use_persona("毒舌老哥")
        self.assertEqual(p.prompt, "你是毒舌老哥")
        self.assertEqual({m.slug for m in self.c.search_memes()}, {"tang-ping", "da-gong-ren"})
        self.assertEqual(self.c.search_stickers("震惊")[0].id, STICKER)
        self.assertEqual(self.c.use_persona("温柔姐姐").prompt, "你是温柔姐姐")
        self.assertEqual([m.slug for m in self.c.search_memes()], ["yyds"])
        count = len(self.c.keys.list())
        before = self.c.request_count
        self.assertEqual(self.c.use_persona("毒舌老哥").title, "毒舌老哥")
        self.assertEqual(self.c.request_count, before)
        self.assertEqual(len(self.c.keys.list()), count)

    def test_a_key_saved_by_hand_switches_with_no_login(self):
        self.c.use_persona("温柔姐姐")
        secret = next(self.c.keys.secret(k.name) for k in self.c.keys.local() if k.persona_title == "温柔姐姐")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            other = GengWiki(base_url=API, site_url=SITE, home=d)
            other.keys.add("手动", secret)
            self.assertEqual(other.use_persona("温柔姐姐").prompt, "你是温柔姐姐")
            self.assertEqual([p.title for p in other.personas("姐姐")], ["温柔姐姐"])
            other.close()

    def test_rotate_and_revoke(self):
        k = self.key()
        old = self.c.keys.secret(k.name)
        self.c.search_memes()
        rotated = self.c.keys.rotate(k.name)
        self.assertEqual(rotated.name, k.name)
        self.assertNotEqual(self.c.keys.secret(k.name), old)
        self.c.refresh()
        self.assertEqual(len(self.c.search_memes()), 6)
        with self.assertRaises(AuthError):
            self.c._http.json("GET", f"{API}/v1/persona", token=old)
        secret = self.c.keys.secret(k.name)
        self.c.keys.revoke(k.name)
        with self.assertRaises(AuthError):
            self.c._http.json("GET", f"{API}/v1/me/usage", token=secret)
        self.assertNotIn(k.name, {x.name for x in self.c.keys.local()})

    def test_stickers_and_image(self):
        self.key()
        pack = self.c.sticker_packs()[0]
        self.assertEqual((pack.id, pack.tags, len(pack.stickers)), (PACK, ["可爱", "动物"], 2))
        path = self.c.sticker_image(STICKER)
        self.assertEqual(path.suffix, ".png")
        self.assertTrue(path.read_bytes().startswith(b"\x89PNG"))

    def test_lexicons_usage_and_rate_limit(self):
        self.key()
        lex = self.c.create_lexicon(f"词库{uuid.uuid4().hex[:6]}", "说明")
        e = self.c.add_lexicon_entry(lex.id, "摆烂", aliases=["bailan"], note="不想努力", tags=["状态"])
        self.assertEqual(self.c.lexicon_entries(lex.id), [e])
        self.c.refresh()
        self.assertEqual(self.c.lexicon_entries(lex.id), [e])  # what we cached equals what the server stored
        self.assertEqual(self.c.search_lexicons("BAILAN"), [e])
        self.assertEqual(self.c.lexicons()[0].entries, 1)
        self.assertEqual(self.c.rate_limit().per_minute, 600)
        self.assertEqual(self.c.usage()["per_day"], 100000)

    def test_tools_and_sync(self):
        self.key()
        self.assertEqual(json.loads(self.c.tools.call("search_memes", {"q": "躺平"}))[0]["slug"], "tang-ping")
        self.assertEqual(json.loads(self.c.tools.call("search_stickers", {"q": "震惊"}))[0]["caption"], "震惊")
        s = self.c.sync(images=True)
        self.assertEqual((s["memes"], s["stickers"], s["images"]), (6, 2, 2))
        self.assertEqual(self.c.sync(images=True)["requests"], 0)


if __name__ == "__main__":
    unittest.main()
