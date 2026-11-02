import os
import stat
import tempfile
import unittest
from pathlib import Path

from gengwiki import GengWikiError
from gengwiki._keyring import Keyring


class KeyringTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(d.cleanup)
        self.path = Path(d.name) / "keys.json"
        self.ring = Keyring(self.path)

    def test_edit_persists_without_leaving_a_temp_file(self):
        self.assertEqual(self.ring.read(), {"keys": {}})
        with self.ring.edit() as d:
            d["keys"]["人设"] = {"key": "x"}
        self.assertEqual(Keyring(self.path).read()["keys"]["人设"], {"key": "x"})
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["keys.json"])

    @unittest.skipIf(os.name == "nt", "Windows has no POSIX modes")
    def test_only_the_owner_can_read_it(self):
        with self.ring.edit() as d:
            d["current"] = "a"
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_corrupt_file_is_never_overwritten(self):
        self.path.write_text("{oops", "utf-8")
        with self.assertRaises(GengWikiError):
            with self.ring.edit() as d:
                d["current"] = "a"
        self.assertEqual(self.path.read_text("utf-8"), "{oops")


if __name__ == "__main__":
    unittest.main()
