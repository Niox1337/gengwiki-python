from gengwiki import AuthError
from tests.fake import PNG
from tests.test_memes import Base


class PersonalTest(Base):
    def test_add_and_remove_each_kind(self):
        c = self.client()
        self.assertEqual(c.add_word("绝绝子", "很绝")["term"], "绝绝子")
        self.assertEqual(c.add_sticker(PNG, "开心").pack_title, "我的表情包")
        self.assertEqual(c.add_persona("小猫", "你是一只猫")["title"], "小猫")
        self.assertEqual(c.add_person("张三", "群主", ["收到"])["name"], "张三")
        self.assertEqual([c.remove_word("绝绝子"), c.remove_sticker("开心"), c.remove_persona("小猫"), c.remove_person("张三")], [1, 1, 1, 1])
        self.assertEqual(c.remove_word("绝绝子"), 0)

    def test_a_write_makes_the_next_read_refetch(self):
        c = self.client()
        c.sticker_packs()
        before = c.request_count
        c.add_sticker(PNG, "开心")
        c.sticker_packs()
        self.assertEqual(c.request_count, before + 2)

    def test_writing_needs_a_key(self):
        with self.assertRaises(AuthError):
            self.client(key=None).add_word("绝绝子")

    def test_guest_memes_off_keeps_memes_out_but_the_notice_in(self):
        c = self.client(key=None, guest_memes=False)
        t = c.turn("躺平是什么梗", memes=True)
        self.assertNotIn("<memes>", t.prompt)
        self.assertFalse(t.memes)
        self.assertIn(f"{self.url}/me", t.notice)
        self.assertEqual(c.match_memes("躺平"), [])
        self.assertEqual(c.meme_prompt("躺平"), "")
        self.assertIn("<memes>", self.client(key=None).turn("躺平是什么梗", memes=True).prompt)

    def test_my_words_named_in_the_message_reach_the_prompt(self):
        c = self.client()
        lex = c.create_lexicon("我的词库")
        c.add_lexicon_entry(lex.id, "绝绝子", note="很绝")
        self.assertIn("绝绝子：很绝", c.turn("今天真是绝绝子").prompt)
        self.assertNotIn("<words>", c.turn("你好").prompt)
