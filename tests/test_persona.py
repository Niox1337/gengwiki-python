import time
import unittest
from unittest import mock

from gengwiki.client import TTL_LIST, TTL_MISSING
from tests.fake import KEY_A, PERSONA_A
from tests.test_memes import Base


class PersonaTest(Base):
    def test_cached_across_clients(self):
        p = self.client().persona()
        self.assertEqual((p.id, p.title), (PERSONA_A, "毒舌老哥"))
        self.assertEqual(p.as_message(), {"role": "system", "content": "你是毒舌老哥"})
        self.assertEqual(self.client().persona().prompt, "你是毒舌老哥")
        self.assertEqual(self.fake.count("/v1/persona"), 1)

    def test_no_persona_is_none_and_remembered(self):
        self.fake.keys[KEY_A]["persona"] = None
        c = self.client()
        self.assertIsNone(c.persona())
        self.assertIsNone(c.persona())
        self.assertEqual(self.fake.count("/v1/persona"), 1)

    def test_an_edit_and_a_takedown_arrive_with_the_list(self):
        c = self.client()
        c.persona()
        self.fake.personas[PERSONA_A]["prompt"] = "改过了"
        self.assertEqual(c.persona().prompt, "你是毒舌老哥")
        now = time.time()
        with mock.patch("time.time", return_value=now + TTL_LIST + 1):
            self.assertEqual(c.persona().prompt, "改过了")
        taken = self.fake.personas.pop(PERSONA_A)
        with mock.patch("time.time", return_value=now + 2 * TTL_LIST + 2):
            self.assertIsNone(c.persona())
        self.fake.personas[PERSONA_A] = taken
        with mock.patch("time.time", return_value=now + 2 * TTL_LIST + TTL_MISSING + 3):
            self.assertEqual(c.persona().prompt, "改过了")

    def test_refresh_reads_it_again_at_once(self):
        c = self.client()
        c.persona()
        self.fake.personas[PERSONA_A]["prompt"] = "改过了"
        c.refresh()
        self.assertEqual(c.persona().prompt, "改过了")


if __name__ == "__main__":
    unittest.main()
