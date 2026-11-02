import unittest

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


if __name__ == "__main__":
    unittest.main()
