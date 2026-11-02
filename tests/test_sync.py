import unittest

from tests.fake import KEY_B, STICKER
from tests.test_memes import Base


class SyncTest(Base):
    def test_after_sync_everything_works_with_the_server_down(self):
        c = self.client()
        s = c.sync(images=True)
        self.assertEqual((s["memes"], s["stickers"], s["images"]), (2, 1, 1))
        self.assertEqual(s["requests"], c.request_count)
        self.fake.status = 500
        before = c.request_count
        self.assertEqual(c.meme("tang-ping").title, "躺平")
        self.assertEqual(c.persona().title, "毒舌老哥")
        self.assertEqual(c.trending(limit=1)[0].slug, "tang-ping")
        self.assertEqual(c.search_stickers("震惊")[0].id, STICKER)
        self.assertTrue(c.sticker_image(STICKER).exists())
        self.assertEqual(c.request_count, before)

    def test_second_sync_is_free(self):
        c = self.client()
        c.sync()
        self.assertEqual(c.sync()["requests"], 0)

    def test_missing_scopes_are_skipped(self):
        self.fake.keys[KEY_B]["scopes"] = ["memes:read"]
        self.assertEqual(self.client(KEY_B).sync()["memes"], 1)


if __name__ == "__main__":
    unittest.main()
