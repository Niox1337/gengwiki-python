import json
from unittest import mock

from gengwiki import client as client_module
from tests.test_memes import Base


class BackupTest(Base):
    def setUp(self):
        super().setUp()
        self.fake.backup = [
            {"slug": "x", "title": "哈基米", "aliases": ["hjm"], "summary": "来源 出自\n赛马娘<b>", "keywords": []},
            {"slug": "y", "title": "哈基米南北绿豆", "aliases": [], "summary": "一首歌"},
        ]
        patcher = mock.patch.object(client_module, "BACKUP_URL", f"{self.url}/backup")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_exact_matches_only_cleaned_and_cached(self):
        c = self.client()
        found = c.backup_memes("哈基米")
        self.assertEqual([(m.title, m.slug, m.summary) for m in found], [("哈基米", "", "出自 赛马娘＜b>")])
        self.assertEqual([m.title for m in c.backup_memes("HJM")], ["哈基米"])
        c.backup_memes("哈基米")
        self.assertEqual(c.backup_memes("没有这个"), [])
        c.backup_memes("没有这个")
        self.assertEqual(self.fake.count("/backup"), 3)  # a miss is kept too

    def test_an_outage_answers_nothing_and_pauses(self):
        c = self.client()
        self.fake.status = 500
        self.assertEqual(c.backup_memes("哈基米"), [])
        self.fake.status = None
        self.assertEqual(c.backup_memes("哈基米"), [])
        self.assertEqual(self.fake.count("/backup"), 1)

    def test_tools_fall_back_only_when_on(self):
        off = self.client(backup=False)
        self.assertEqual(json.loads(off.tools.call("search_memes", {"q": "哈基米"})), [])
        self.assertEqual(self.fake.count("/backup"), 0)
        on = self.client(backup=True)
        self.assertEqual(json.loads(on.tools.call("search_memes", {"q": "哈基米"})), [{"title": "哈基米", "aliases": ["hjm"], "summary": "出自 赛马娘＜b>"}])
        self.assertEqual(json.loads(on.tools.call("get_meme", {"slug": "哈基米"}))["title"], "哈基米")
        self.assertEqual(json.loads(on.tools.call("get_meme", {"slug": "没有"}))["error"]["code"], "not_found")
        on.tools.call("search_memes", {"q": "躺平"})  # this wiki has it, so it never goes out
        self.assertEqual(self.fake.count("/backup"), 2)

    def test_explain_answers_a_question_about_a_meme(self):
        c = self.client(backup=True)
        self.assertIn("- 躺平（摆烂）：", c.explain("请问“躺平”是什么梗啊"))
        self.assertIn("- 哈基米（hjm）：出自 赛马娘", c.explain("哈基米这个梗啥意思"))
        for text in ("这是什么梗", "今天好累", "最近流行什么梗"):
            self.assertEqual(c.explain(text), "")
        self.assertIn("没有资料，不用再搜它", c.explain("没有这个是什么梗"))  # or the model explains from memory
        self.assertEqual(self.fake.count("/backup"), 2)
        self.assertIn("对方在问「哈基米」是什么梗", c.turn("哈基米这个梗啥意思").prompt)  # hosts get it without calling explain
        self.assertNotIn("对方在问", c.turn("今天好累").prompt)
