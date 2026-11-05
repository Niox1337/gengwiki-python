import contextlib
import io
import os
import subprocess
import sys
from unittest import mock

from gengwiki import GengWiki
from gengwiki.__main__ import main
from tests.fake import KEY_A, KEY_B
from tests.test_memes import Base


class CliTest(Base):
    def run_cli(self, *argv, key=None, password="correct horse", secret=KEY_A):
        env = {"GENGWIKI_API_URL": self.url, "GENGWIKI_SITE_URL": self.url, "GENGWIKI_HOME": self.dir.name, "GENGWIKI_API_KEY": key or ""}
        out, err = io.StringIO(), io.StringIO()
        answers = lambda prompt: password if "密码" in prompt else secret
        with mock.patch.dict("os.environ", env), mock.patch("getpass.getpass", answers), mock.patch("builtins.input", lambda p: "me@example.com"):
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(list(argv))
        return code, out.getvalue() + err.getvalue()

    def test_first_run_from_nothing_to_a_search(self):
        code, text = self.run_cli("status")
        self.assertEqual(code, 0)
        self.assertIn("/me", text)
        self.assertEqual(self.run_cli("keys", "add", "老哥")[0], 0)
        code, text = self.run_cli("search", "躺平")
        self.assertEqual(code, 0)
        self.assertIn("tang-ping", text)
        self.assertIn("* 老哥", self.run_cli("keys")[1])
        self.assertIn("毒舌老哥", self.run_cli("status")[1])

    def test_status_says_what_the_key_can_do(self):
        self.run_cli("keys", "add", "老哥")
        self.assertIn("梗 2 个，表情", self.run_cli("status")[1])
        self.fake.keys[KEY_A]["scopes"] = ["memes:read"]
        with GengWiki(KEY_A, base_url=self.url, site_url=self.url, home=self.dir.name) as c:
            c.refresh()
        code, text = self.run_cli("status")
        self.assertEqual(code, 0)
        self.assertIn("缺权限", text)
        self.assertIn("people:read", text)

    def test_key_never_shows_except_when_asked(self):
        self.run_cli("keys", "add", "老哥")
        for argv in (("keys",), ("status",), ("search", "躺平")):
            self.assertNotIn(KEY_A, self.run_cli(*argv)[1], argv)
        self.assertEqual(self.run_cli("keys", "secret", "老哥")[1].strip(), KEY_A)

    def test_switch_keys_and_personas(self):
        self.run_cli("keys", "add", "a")
        self.run_cli("keys", "add", "b", secret=KEY_B)
        self.assertEqual(self.run_cli("use", "温柔姐姐")[0], 0)
        self.assertIn("温柔姐姐", self.run_cli("status")[1])
        self.assertEqual(self.run_cli("keys", "use", "a")[0], 0)
        self.assertIn("毒舌老哥", self.run_cli("status")[1])
        self.assertIn("* a", self.run_cli("keys")[1])

    def test_login_then_account_commands(self):
        self.assertEqual(self.run_cli("login")[0], 0)
        self.assertIn("gwk_live_aaaaaa", self.run_cli("keys", "remote")[1])
        self.run_cli("keys", "add", "a")
        self.assertEqual(self.run_cli("keys", "rotate", "a")[0], 0)
        self.assertEqual(self.run_cli("keys", "revoke", "a")[0], 0)
        self.assertEqual(self.run_cli("keys", "remove", "a")[0], 0)
        self.assertEqual(self.run_cli("logout")[0], 0)

    def test_failures_print_a_message_and_exit_1(self):
        for argv, expected in (
            (("search", "躺平"), "no API key"),
            (("login",), "unauthorized"),
            (("keys", "use", "nope"), "no key saved"),
            (("keys", "secret", "nope"), "no key saved"),
        ):
            code, text = self.run_cli(*argv, password="wrong")
            self.assertEqual(code, 1, argv)
            self.assertIn(expected, text, argv)
        code, text = self.run_cli("keys", "add", "x", secret="sk-not-ours")
        self.assertEqual(code, 1)

    def test_reads_and_sync(self):
        self.run_cli("keys", "add", "a")
        self.assertIn("躺平的正文", self.run_cli("meme", "摆烂")[1])
        self.assertIn("躺平的场景", self.run_cli("meme", "摆烂")[1])
        self.assertIn("tang-ping", self.run_cli("trending")[1])
        self.assertIn("网络  2", self.run_cli("tags")[1])
        self.assertIn("还没有订阅", self.run_cli("subscribe")[1])
        self.assertIn("tang-ping", self.run_cli("subscribe", "网络")[1])
        self.assertIn("网络", self.run_cli("subscribe")[1])
        self.assertIn("已退订", self.run_cli("unsubscribe", "网络")[1])
        self.assertIn("没有订阅", self.run_cli("unsubscribe", "网络")[1])
        self.assertIn("温柔姐姐", self.run_cli("personas", "姐姐")[1])
        self.assertIn("梗 2 个", self.run_cli("sync", "--images")[1])

    def test_empty_results_say_so(self):
        self.run_cli("keys", "add", "a")
        self.assertIn("没有找到", self.run_cli("search", "完全不存在")[1])
        self.assertIn("没有找到", self.run_cli("personas", "完全不存在")[1])

    def test_a_pipe_that_cannot_hold_chinese_still_gets_readable_text(self):
        env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
        out = subprocess.run([sys.executable, "-m", "gengwiki", "--help"], capture_output=True, env=env, check=False).stdout
        self.assertIn("梗Wiki", out.decode("utf-8"))

    def test_no_command_prints_help(self):
        code, text = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn("usage", text)
