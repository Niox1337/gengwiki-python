import json
import os
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from gengwiki import GengWiki, GengWikiError
from gengwiki._keyring import Keyring

_EDITOR = """
import sys
from pathlib import Path
from gengwiki._keyring import Keyring

ring = Keyring(Path(sys.argv[1]))
for i in range(25):
    with ring.edit() as d:
        d["keys"][f"{sys.argv[2]}-{i}"] = {"key": "x"}
    ring.read()
"""


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
        self.assertEqual(sorted(p.name for p in self.path.parent.iterdir()), ["keys.json", "keys.json.lock"])

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

    def test_threads_saving_at_once_all_keep_their_edit(self):
        def work(n):
            ring = Keyring(self.path)
            for i in range(10):
                with ring.edit() as d:
                    d["keys"][f"{n}-{i}"] = {"key": "x"}

        threads = [threading.Thread(target=work, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(self.ring.read()["keys"]), 80)

    def test_processes_saving_at_once_all_keep_their_edit(self):
        children = [subprocess.Popen([sys.executable, "-c", _EDITOR, str(self.path), str(n)], stderr=subprocess.PIPE, text=True) for n in range(4)]
        for child in children:
            self.assertEqual(child.communicate(timeout=60)[1], "")
            self.assertEqual(child.returncode, 0)
        self.assertEqual(len(self.ring.read()["keys"]), 100)


class FakeKeychain:
    def __init__(self):
        self.saved = {}
        self.reads = 0
        self.refuse = False

    def set_password(self, service, ref, secret):
        if self.refuse:
            raise RuntimeError("locked")
        self.saved[service, ref] = secret

    def get_password(self, service, ref):
        self.reads += 1
        return self.saved.get((service, ref))

    def delete_password(self, service, ref):
        del self.saved[service, ref]


class KeychainTest(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(d.cleanup)
        self.dir = Path(d.name)
        self.path = self.dir / "keys.json"
        self.keychain = FakeKeychain()
        patcher = mock.patch("gengwiki._keyring._keychain", lambda: self.keychain)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.ring = Keyring(self.path)

    def save(self, name="a", secret="gwk_secret"):
        with self.ring.edit() as d:
            d["keys"][name] = {"key": secret, "id": "i"}

    def test_the_secret_leaves_the_file_and_still_reads_back(self):
        self.save()
        with self.ring.edit() as d:
            d["session"] = {"token": "jwt_secret", "expires_at": 1}
        text = self.path.read_text("utf-8")
        self.assertNotIn("gwk_secret", text)
        self.assertNotIn("jwt_secret", text)
        fresh = Keyring(self.path).read()
        self.assertEqual(fresh["keys"]["a"]["key"], "gwk_secret")
        self.assertEqual(fresh["keys"]["a"]["id"], "i")
        self.assertEqual(fresh["session"]["token"], "jwt_secret")

    def test_an_unrelated_edit_writes_nothing_to_the_keychain(self):
        self.save()
        before = dict(self.keychain.saved)
        with self.ring.edit() as d:
            d["current"] = "a"
        self.assertEqual(self.keychain.saved, before)

    def test_reading_often_asks_the_keychain_once(self):
        self.save()
        ring = Keyring(self.path)
        for _ in range(5):
            ring.read()
        self.assertEqual(self.keychain.reads, 1)

    def test_a_replaced_or_removed_secret_leaves_the_keychain(self):
        self.save()
        self.save(secret="gwk_new")
        self.assertEqual(list(self.keychain.saved.values()), ["gwk_new"])
        self.assertEqual(Keyring(self.path).read()["keys"]["a"]["key"], "gwk_new")
        with self.ring.edit() as d:
            del d["keys"]["a"]
        self.assertEqual(self.keychain.saved, {})

    def test_another_process_rotating_a_key_is_seen_here(self):
        self.save()
        other = Keyring(self.path)
        self.assertEqual(other.read()["keys"]["a"]["key"], "gwk_secret")
        self.save(secret="gwk_new")
        self.assertEqual(other.read()["keys"]["a"]["key"], "gwk_new")

    def test_a_plaintext_file_moves_over_on_the_next_edit(self):
        self.path.write_text(json.dumps({"keys": {"a": {"key": "gwk_secret"}}}), "utf-8")
        self.assertEqual(self.ring.read()["keys"]["a"]["key"], "gwk_secret")
        with self.ring.edit() as d:
            d["current"] = "a"
        self.assertNotIn("gwk_secret", self.path.read_text("utf-8"))
        self.assertEqual(self.ring.read()["keys"]["a"]["key"], "gwk_secret")

    def test_a_secret_the_keychain_refuses_stays_in_the_file(self):
        self.keychain.refuse = True
        with self.assertLogs("gengwiki", "WARNING"):
            self.save()
        self.assertIn("gwk_secret", self.path.read_text("utf-8"))
        self.assertEqual(self.ring.read()["keys"]["a"]["key"], "gwk_secret")

    def test_a_missing_keychain_is_an_error_and_loses_nothing(self):
        self.save()
        text = self.path.read_text("utf-8")
        with mock.patch("gengwiki._keyring._keychain", lambda: None):
            with self.assertRaisesRegex(GengWikiError, "gengwiki.keychain"):
                Keyring(self.path).read()
            with self.assertRaises(GengWikiError):
                with Keyring(self.path).edit() as d:
                    d["current"] = "a"
        self.assertEqual(self.path.read_text("utf-8"), text)

    def test_the_client_works_the_same_on_top_of_it(self):
        secret = "gwk_live_aaaaaa" + "0" * 42
        with GengWiki(secret, base_url="http://127.0.0.1:9", home=self.dir) as c:
            c.keys.add("a", secret)
            self.assertNotIn(secret, (c.home / "keys.json").read_text("utf-8"))
        with GengWiki(base_url="http://127.0.0.1:9", home=self.dir) as c:
            self.assertEqual(c._key, secret)
            self.assertEqual(c.keys.secret("a"), secret)
            self.assertTrue(c.keys.local()[0].current)
            c.keys.remove("a")
        self.assertEqual(self.keychain.saved, {})


if __name__ == "__main__":
    unittest.main()
