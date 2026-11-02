import unittest

from gengwiki import NotFoundError
from tests.fake import PACK, PNG, STICKER
from tests.test_memes import Base


class StickerTest(Base):
    def test_every_search_is_local(self):
        c = self.client()
        s = c.search_stickers("震惊")[0]
        self.assertEqual((s.id, s.pack_id, s.pack_title), (STICKER, PACK, "猫猫"))
        self.assertTrue(s.url.endswith(f"/v1/stickers/{STICKER}/image"))
        self.assertEqual(len(c.search_stickers("可爱")), 1)
        self.assertEqual(c.search_stickers("没有"), [])
        self.assertEqual(c.sticker_packs()[0].stickers[0].caption, "震惊")
        self.assertEqual(c.request_count, 1)

    def test_image_downloads_once_and_without_a_key(self):
        c = self.client(key=None)
        path = c.sticker_image(STICKER)
        self.assertEqual((path.read_bytes(), path.suffix), (PNG, ".png"))
        self.assertEqual(self.client().sticker_image(STICKER), path)
        self.assertEqual(self.fake.count("/v1/stickers/"), 1)

    def test_image_id_cannot_escape_the_folder(self):
        with self.assertRaises(ValueError):
            self.client().sticker_image("../../keys")
        self.assertEqual(self.fake.count(), 0)

    def test_missing_image_raises(self):
        with self.assertRaises(NotFoundError):
            self.client().sticker_image("00000000-0000-0000-0000-000000000000")


if __name__ == "__main__":
    unittest.main()
