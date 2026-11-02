import time
import unittest
from unittest import mock

from gengwiki import AccountApiUnavailable, AuthError, GengWiki, NotFoundError
from gengwiki._store import namespace
from gengwiki.client import TTL_CATALOG_MISS
from tests.fake import KEY_A, KEY_B, PACK, PERSONA_A, PERSONA_B
from tests.test_memes import Base


class LocalKeysTest(Base):
    def test_saved_key_is_used_by_new_clients(self):
        c = self.client(key=None)
        k = c.keys.add("老哥", KEY_A)
        self.assertTrue(k.current)
        self.assertEqual(k.prefix, KEY_A[:15])
        self.assertEqual(self.client(key=None).search_memes()[0].slug, "tang-ping")

    def test_explicit_key_beats_the_saved_one_and_is_not_saved(self):
        c = self.client(key=None)
        c.keys.add("老哥", KEY_A)
        other = self.client(KEY_B)
        self.assertEqual([m.slug for m in other.search_memes()], ["yyds"])
        self.assertEqual([k.name for k in other.keys.local()], ["老哥"])

    def test_env_key_works(self):
        with mock.patch.dict("os.environ", {"GENGWIKI_API_KEY": KEY_B}):
            self.assertEqual([m.slug for m in self.client(key=None).search_memes()], ["yyds"])

    def test_refuses_junk_and_overwrites(self):
        c = self.client(key=None)
        with self.assertRaises(ValueError):
            c.keys.add("x", "sk-not-ours")
        c.keys.add("x", KEY_A)
        c.keys.add("x", KEY_A)  # same key again is fine
        with self.assertRaises(ValueError):
            c.keys.add("x", KEY_B)
        self.assertEqual(c.keys.secret("x"), KEY_A)

    def test_use_and_remove(self):
        c = self.client(key=None)
        c.keys.add("a", KEY_A)
        c.keys.add("b", KEY_B)
        self.assertTrue(c.keys.use("b").current)
        self.assertEqual([m.slug for m in c.search_memes()], ["yyds"])
        self.assertEqual([m.slug for m in self.client(key=None).search_memes()], ["yyds"])
        with self.assertRaises(NotFoundError):
            c.keys.use("nope")
        c.keys.remove("b")
        self.assertEqual([k.name for k in c.keys.local()], ["a"])

    def test_unknown_name_raises_the_sdk_error(self):
        with self.assertRaises(NotFoundError):
            self.client(key=None).keys.secret("nope")

    def test_removing_the_current_key_stops_this_client_using_it(self):
        c = self.client(key=None)
        c.keys.add("a", KEY_A)
        c.keys.add("b", KEY_B)
        c.keys.remove("a")
        with self.assertRaisesRegex(AuthError, r"keys\.use.*'b'"):
            c.search_memes()

    def test_no_key_says_where_to_get_one(self):
        with self.assertRaisesRegex(AuthError, "/me"):
            self.client(key=None).search_memes()

    def test_a_host_never_sees_keys_saved_for_another(self):
        self.client(key=None).keys.add("a", KEY_A)
        c = GengWiki(base_url="http://127.0.0.1:9", site_url=self.url, home=self.dir.name)
        self.addCleanup(c.close)
        self.assertEqual(c.keys.local(), [])


class SwitchPersonaTest(Base):
    def saved(self):
        c = self.client(key=None)
        c.keys.add("a", KEY_A)
        c.keys.add("b", KEY_B)
        return c

    def test_switch_changes_prompt_and_scope(self):
        c = self.saved()
        self.assertEqual(c.use_persona("温柔姐姐").prompt, "你是温柔姐姐")
        self.assertEqual([m.slug for m in c.search_memes()], ["yyds"])
        self.assertEqual(c.persona().id, PERSONA_B)
        self.assertEqual(c.use_persona(PERSONA_A).title, "毒舌老哥")
        self.assertEqual({m.slug for m in c.search_memes()}, {"tang-ping", "yyds"})

    def test_switching_back_and_forth_is_free_once_seen(self):
        c = self.saved()
        c.use_persona("毒舌老哥")
        c.use_persona("温柔姐姐")
        c.search_memes()
        before = c.request_count
        for _ in range(5):
            c.use_persona("毒舌老哥")
            c.persona()
            c.use_persona("温柔姐姐")
            c.persona()
            c.search_memes("yyds")
        self.assertEqual(c.request_count, before)

    def test_choice_survives_a_restart(self):
        self.saved().use_persona("温柔姐姐")
        c = self.client(key=None)
        self.assertEqual(c.persona().title, "温柔姐姐")
        self.assertEqual(c.request_count, 0)

    def test_failed_switch_keeps_the_old_persona(self):
        c = self.saved()
        with self.assertRaisesRegex(NotFoundError, "login|log in"):
            c.use_persona("没有这个人设")
        self.assertEqual(c.persona().title, "毒舌老哥")

    def test_revoked_key_is_skipped(self):
        c = self.saved()
        self.fake.keys[KEY_A]["revoked"] = True
        self.assertEqual(c.use_persona("温柔姐姐").title, "温柔姐姐")

    def test_login_creates_the_key_with_the_persona_scope(self):
        c = self.client(key=None)
        c.keys.login("me@example.com", "correct horse")
        self.assertEqual(c.use_persona("毒舌老哥").prompt, "你是毒舌老哥")
        made = next(k for k in self.fake.keys.values() if k["name"] == "毒舌老哥")
        self.assertEqual((made["persona"], made["memes"], made["packs"]), (PERSONA_A, ["tang-ping"], [PACK]))
        self.assertEqual([m.slug for m in c.search_memes()], ["tang-ping"])
        count = len(self.fake.keys)
        c.use_persona("毒舌老哥")
        self.assertEqual(len(self.fake.keys), count)  # the second time reuses it

    def test_catalog_is_cached_and_filterable(self):
        c = self.client(key=None)
        self.assertEqual(len(c.personas()), 2)
        self.assertEqual([p.title for p in c.personas("姐姐")], ["温柔姐姐"])
        self.assertEqual(c.personas("姐姐")[0].memes[0]["slug"], "yyds")
        self.assertEqual(self.fake.count("/api/personas"), 1)

    def test_newly_published_persona_is_found_without_waiting_a_day(self):
        published = self.fake.personas.pop(PERSONA_B)
        c = self.client(key=None)
        c.keys.login("me@example.com", "correct horse")
        self.assertEqual(len(c.personas()), 1)
        with self.assertRaises(NotFoundError):
            c.use_persona("温柔姐姐")
        self.assertEqual(self.fake.count("/api/personas"), 1)  # just read, so the miss sends nothing
        self.fake.personas[PERSONA_B] = published
        later = time.time() + TTL_CATALOG_MISS + 1
        with mock.patch("time.time", return_value=later):
            self.assertEqual(c.use_persona("温柔姐姐").prompt, "你是温柔姐姐")
        self.assertEqual(self.fake.count("/api/personas"), 2)

    def test_empty_catalog_is_checked_again(self):
        hidden, self.fake.personas = self.fake.personas, {}
        c = self.client(key=None)
        self.assertEqual(c.personas(), [])
        self.assertEqual(c.personas(), [])
        self.assertEqual(self.fake.count("/api/personas"), 1)  # repeating a miss within the minute sends nothing
        self.fake.personas = hidden
        later = time.time() + TTL_CATALOG_MISS + 1
        with mock.patch("time.time", return_value=later):
            self.assertEqual(len(c.personas()), 2)
            self.assertEqual(len(c.personas()), 2)
        self.assertEqual(self.fake.count("/api/personas"), 2)

    def test_hit_in_an_old_catalog_sends_nothing(self):
        c = self.client(key=None)
        c.personas()
        later = time.time() + TTL_CATALOG_MISS + 1
        with mock.patch("time.time", return_value=later):
            self.assertEqual([p.title for p in c.personas("姐姐")], ["温柔姐姐"])
        self.assertEqual(self.fake.count("/api/personas"), 1)

    def test_hidden_catalog_falls_back_to_saved_keys(self):
        self.fake.account_open = False
        c = self.saved()
        c.use_persona("温柔姐姐")
        self.assertEqual({p.title for p in c.personas()}, {"毒舌老哥", "温柔姐姐"})
        c.personas()
        self.assertEqual(self.fake.count("/api/personas"), 1)


class AccountTest(Base):
    def logged_in(self):
        c = self.client(key=None)
        c.keys.login("me@example.com", "correct horse")
        return c

    def test_wrong_password(self):
        c = self.client(key=None)
        with self.assertRaises(AuthError):
            c.keys.login("me@example.com", "wrong")
        self.assertFalse(c.keys.logged_in)

    def test_password_is_not_stored(self):
        c = self.logged_in()
        text = (c.home / "keys.json").read_text("utf-8")
        self.assertNotIn("correct horse", text)
        self.assertTrue(self.client(key=None).keys.logged_in)

    def test_needs_login_before_any_request(self):
        c = self.client(key=None)
        with self.assertRaisesRegex(AuthError, "login"):
            c.keys.list()
        self.assertEqual(c.request_count, 0)

    def test_expired_session_is_cleared(self):
        c = self.logged_in()
        with c._keyring.edit() as d:
            d["session"]["token"] = "stale"
        with self.assertRaises(AuthError):
            c.keys.list()
        self.assertFalse(c.keys.logged_in)

    def test_hidden_account_api_says_what_to_do(self):
        self.fake.account_open = False
        with self.assertRaisesRegex(AccountApiUnavailable, r"keys\.add"):
            self.client(key=None).keys.login("me@example.com", "correct horse")

    def test_create_saves_the_one_time_secret(self):
        c = self.logged_in()
        k = c.keys.create("新的", memes=["yyds"])
        secret = c.keys.secret("新的")
        self.assertEqual(self.fake.keys[secret]["memes"], ["yyds"])
        self.assertEqual(k.prefix, secret[:15])
        self.assertTrue(k.current)  # first key, so it is the current one
        self.assertEqual([m.slug for m in c.search_memes()], ["yyds"])

    def test_create_with_a_taken_name_keeps_both(self):
        c = self.logged_in()
        a, b = c.keys.create("同名"), c.keys.create("同名")
        self.assertNotEqual(a.name, b.name)
        self.assertNotEqual(c.keys.secret(a.name), c.keys.secret(b.name))

    def test_list_hides_revoked(self):
        c = self.logged_in()
        self.fake.keys[KEY_B]["revoked"] = True
        self.assertEqual({k.name for k in c.keys.list()}, {"a"})
        self.assertEqual({k.name for k in c.keys.list(include_revoked=True)}, {"a", "b"})

    def test_rotate_keeps_the_cache_and_switches_the_client(self):
        c = self.logged_in()
        c.keys.add("a", KEY_A)
        c.search_memes()
        before = self.fake.count("/v1/")
        k = c.keys.rotate("a")
        self.assertEqual(k.name, "a")
        self.assertTrue(k.current)
        self.assertNotEqual(c.keys.secret("a"), KEY_A)
        c.search_memes()
        self.assertEqual(self.fake.count("/v1/"), before)  # cache moved over
        c.refresh()
        c.search_memes()  # and the new secret works
        self.assertEqual(self.fake.count("/v1/"), before + 1)
        self.assertTrue(self.fake.keys[KEY_A]["revoked"])

    def test_rotate_unsaved_key_saves_the_new_secret(self):
        c = self.client(KEY_A)
        c.keys.login("me@example.com", "correct horse")
        k = c.keys.rotate("a")
        self.assertEqual(k.name, "a")
        c.refresh()
        c.search_memes()

    def test_revoke_ends_it_everywhere(self):
        c = self.logged_in()
        c.keys.add("a", KEY_A)
        c.search_memes()
        c.keys.revoke("a")
        self.assertTrue(self.fake.keys[KEY_A]["revoked"])
        self.assertEqual(c.keys.local(), [])
        with self.assertRaises(AuthError):
            c.search_memes()
        self.assertIsNone(c._store.get(namespace(KEY_A), "list"))

    def test_revoke_by_remote_name_and_ambiguity(self):
        c = self.logged_in()
        c.keys.revoke("b")
        self.assertTrue(self.fake.keys[KEY_B]["revoked"])
        c.keys.create("同名")
        c.keys.create("同名")
        # Saved under different names, so forget them to reach the lookup by remote name.
        with c._keyring.edit() as d:
            d["keys"] = {}
        with self.assertRaises(ValueError):
            c.keys.revoke("同名")
        with self.assertRaises(NotFoundError):
            c.keys.revoke("不存在")


if __name__ == "__main__":
    unittest.main()
