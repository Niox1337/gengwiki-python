import tempfile
import unittest
from pathlib import Path

from gengwiki._store import Store


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "cache.sqlite3"
        self.store = Store(self.path)
        self.addCleanup(self.store.close)

    def test_round_trip_survives_reopening(self):
        self.store.put("a", "k", {"标题": [1]})
        self.store.close()
        self.store = Store(self.path)
        hit = self.store.get("a", "k")
        self.assertEqual(hit.value, {"标题": [1]})
        self.assertLess(hit.age, 60)
        self.assertIsNone(self.store.get("b", "k"))

    def test_expire_keeps_the_value(self):
        self.store.put("a", "k", 1)
        self.store.expire("a")
        hit = self.store.get("a", "k")
        self.assertEqual(hit.value, 1)
        self.assertGreater(hit.age, 1e6)

    def test_rename_and_drop(self):
        self.store.put("a", "k", 1)
        self.store.rename("a", "b")
        self.assertIsNone(self.store.get("a", "k"))
        self.assertEqual(self.store.get("b", "k").value, 1)
        self.store.drop("b")
        self.assertIsNone(self.store.get("b", "k"))

    def test_corrupt_file_starts_over(self):
        path = Path(self.dir.name) / "bad.sqlite3"
        path.write_bytes(b"this is not a database, " * 100)
        store = Store(path)
        self.addCleanup(store.close)
        store.put("a", "k", 1)
        self.assertEqual(store.get("a", "k").value, 1)

    def test_closed_db_reads_as_a_miss(self):
        store = Store(Path(self.dir.name) / "x.sqlite3")
        store.close()
        store.put("a", "k", 1)
        self.assertIsNone(store.get("a", "k"))


if __name__ == "__main__":
    unittest.main()
