from gengwiki import AuthError
from tests.fake import KEY_A, meme
from tests.test_memes import Base


class GuestTest(Base):
    def setUp(self):
        super().setUp()
        for i in range(25):
            m = meme(f"m{i}", f"梗{i}", heat=100 - i)
            self.fake.memes[m["slug"]] = m
        for i in range(12):
            pid = f"00000000-0000-0000-0000-{i:012d}"
            self.fake.people[pid] = {"id": pid, "name": f"人{i}", "aliases": [], "tags": [], "bio": "", "quotes": [f"语录{i}"]}

    def test_no_key_reads_the_hot_board_and_ten_people(self):
        c = self.client(key=None)
        self.assertEqual(len(c.search_memes()), 20)
        self.assertEqual(len(c.trending()), 20)
        self.assertEqual(len(c.people()), 10)
        self.assertEqual(len(c.linked_people()), 10)
        self.assertIsNone(c.persona())
        with self.assertRaises(AuthError):
            c.usage()

    def test_first_turn_carries_the_notice_once(self):
        c = self.client(key=None)
        first, second = c.turn("你好"), c.turn("你好")
        self.assertIn(f"{self.url}/me", first.notice)
        self.assertEqual(second.notice, "")
        self.assertEqual(self.client().turn("你好").notice, "")

    def test_guest_copies_never_reach_a_keyed_client(self):
        self.client(key=None).people()
        self.assertEqual(len(self.client(KEY_A).people()), 14)
