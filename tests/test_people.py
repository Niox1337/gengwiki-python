from gengwiki import ForbiddenError, NotFoundError
from tests.fake import KEY_A, KEY_B, LU_XUN, PERSONA_A
from tests.test_memes import Base


class PeopleTest(Base):
    def test_linked_are_the_ones_on_the_key(self):
        c = self.client()
        self.assertEqual([p.name for p in c.linked_people()], ["鲁迅"])
        c.linked_people()
        self.assertEqual(self.fake.count("/v1/people/linked"), 1)
        self.assertEqual(self.client(KEY_B).linked_people(), [])

    def test_all_people_search_locally_and_are_shared_between_keys(self):
        c = self.client()
        self.assertEqual({p.name for p in c.people()}, {"鲁迅", "杜甫"})
        self.assertEqual([p.name for p in c.people("诗人")], ["杜甫"])
        self.assertEqual([p.name for p in c.people("两棵树")], ["鲁迅"])
        self.client(KEY_B).people()
        self.assertEqual(self.fake.count("/v1/people"), 1)

    def test_all_people_walks_every_page(self):
        for i in range(150):
            pid = f"p{i}"
            self.fake.people[pid] = {"id": pid, "name": f"人{i}", "aliases": [], "tags": [], "bio": "", "quotes": []}
        self.assertEqual(len(self.client().people()), 152)
        self.assertEqual(self.fake.count("/v1/people"), 2)

    def test_one_person_by_name_alias_or_id(self):
        c = self.client()
        for wanted in ("鲁迅", "周树人", LU_XUN):
            p = c.person(wanted)
            self.assertEqual((p.name, p.memes[0]["slug"]), ("鲁迅", "tang-ping"))
        with self.assertRaises(NotFoundError):
            c.person("没有这个人")

    def test_scope_is_required(self):
        self.fake.keys[KEY_A]["scopes"] = ["memes:read"]
        with self.assertRaises(ForbiddenError):
            self.client().linked_people()

    def test_creating_a_key_with_a_persona_brings_its_people(self):
        c = self.client()
        c.keys.login("a@b.c", "correct horse")
        c.keys.create("new", persona=PERSONA_A)
        made = next(k for k in self.fake.keys.values() if k["name"] == "new")
        self.assertEqual(made["people"], [LU_XUN])
