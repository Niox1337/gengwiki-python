import gzip
import http.server
import json
import os
import threading
import unittest
from unittest import mock

from gengwiki import _http
from gengwiki._http import Http, check_url
from gengwiki.errors import AuthError, BadResponseError, GengWikiError, NetworkError, RateLimitError, ServerError


class Handler(http.server.BaseHTTPRequestHandler):
    seen: list = []
    fail_first = 0

    def log_message(self, *args):
        pass

    def _send(self, status, body=b"{}", headers=()):
        self.send_response(status)
        for k, v in headers:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        Handler.seen.append((self.path, self.headers.get("Authorization")))
        if self.path == "/401":
            self._send(401, json.dumps({"error": {"code": "unauthorized", "message": "nope"}}).encode())
        elif self.path == "/html404":
            self._send(404, b"<html>")
        elif self.path == "/429":
            self._send(429, b"{}", [("Retry-After", "3600")])
        elif self.path == "/redirect":
            self._send(302, b"", [("Location", "/ok")])
        elif self.path == "/gzip":
            self._send(200, gzip.compress(b'{"a": 1}'), [("Content-Encoding", "gzip")])
        elif self.path == "/cut":
            self.send_response(200)
            self.send_header("Content-Length", "100")
            self.end_headers()
            self.wfile.write(b'{"a"')
        elif self.path == "/badgzip":
            self._send(200, b"not gzip at all", [("Content-Encoding", "gzip")])
        elif self.path == "/flaky" and Handler.fail_first:
            Handler.fail_first -= 1
            self._send(500)
        else:
            self._send(200, b'{"ok": true}')


class HttpTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        Handler.seen.clear()
        self.http = Http(timeout=2)

    def test_typed_error_with_server_code(self):
        with self.assertRaises(AuthError) as c:
            self.http.json("GET", self.base + "/401")
        self.assertEqual(c.exception.code, "unauthorized")

    def test_non_json_error_has_no_code(self):
        with self.assertRaises(GengWikiError) as c:
            self.http.json("GET", self.base + "/html404")
        self.assertIsNone(c.exception.code)

    def test_long_retry_after_is_not_waited_out(self):
        with self.assertRaises(RateLimitError) as c:
            self.http.json("GET", self.base + "/429", retries=3)
        self.assertEqual(c.exception.retry_after, 3600)
        self.assertEqual(self.http.count, 1)

    def test_redirect_never_forwards_the_token(self):
        with self.assertRaises(GengWikiError):
            self.http.json("GET", self.base + "/redirect", token="secret")
        self.assertEqual(len(Handler.seen), 1)

    def test_gzip(self):
        self.assertEqual(self.http.json("GET", self.base + "/gzip"), {"a": 1})

    def test_retry_then_success(self):
        Handler.fail_first = 1
        self.assertEqual(self.http.json("GET", self.base + "/flaky", retries=1), {"ok": True})
        self.assertEqual(self.http.count, 2)

    def test_no_retry_by_default(self):
        Handler.fail_first = 1
        with self.assertRaises(ServerError):
            self.http.json("GET", self.base + "/flaky")
        Handler.fail_first = 0

    def test_connection_refused(self):
        with self.assertRaises(NetworkError):
            self.http.json("GET", "http://127.0.0.1:9/")

    def test_url_check(self):
        self.assertEqual(check_url("https://a.b/"), "https://a.b")
        self.assertEqual(check_url("http://localhost:8081"), "http://localhost:8081")
        self.assertEqual(check_url("http://[::1]:8081"), "http://[::1]:8081")
        for bad in ("http://a.b", "ftp://localhost", "localhost:8081"):
            with self.assertRaises(ValueError):
                check_url(bad)

    def test_response_cut_short_or_damaged_is_a_network_error(self):
        for path in ("/cut", "/badgzip"):
            with self.assertRaises(NetworkError, msg=path):
                self.http.json("GET", f"{self.base}{path}")

    def test_a_proxy_from_the_environment_is_still_used(self):
        env = {"HTTP_PROXY": self.base, "http_proxy": self.base, "NO_PROXY": "", "no_proxy": ""}
        with mock.patch.dict(os.environ, env):
            proxied = Http(timeout=2)
            self.assertEqual(proxied.json("GET", "http://gengwiki.invalid/x"), {"ok": True})
        self.assertEqual(Handler.seen[0][0], "http://gengwiki.invalid/x")

    def test_rows_must_have_the_fields_the_sdk_reads(self):
        shape = [{"slug": str, "stickers": [{"id": str}]}]
        self.assertTrue(_http._fits([], shape))
        self.assertTrue(_http._fits([{"slug": "a", "stickers": [{"id": "b", "new": 1}], "new": 1}], shape))
        for bad in ({}, ["a"], [{}], [{"slug": None, "stickers": []}], [{"slug": "a", "stickers": [{}]}]):
            self.assertFalse(_http._fits(bad, shape), bad)
        with self.assertRaises(BadResponseError):
            self.http.json("GET", self.base + "/ok", expect={"missing": str})


class KeepAliveHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    connections = 0
    seen: list = []

    def log_message(self, *args):
        pass

    def setup(self):
        KeepAliveHandler.connections += 1
        super().setup()

    def _answer(self):
        KeepAliveHandler.seen.append((self.command, self.path))
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")
        # Goes away without saying so, as a server does with a connection left idle too long.
        self.close_connection = self.path == "/drop"

    do_GET = do_POST = _answer


class KeepAliveTest(unittest.TestCase):
    def setUp(self):
        KeepAliveHandler.connections = 0
        KeepAliveHandler.seen = []
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), KeepAliveHandler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.http = Http(timeout=2)
        self.addCleanup(self.http.close)

    def test_requests_share_one_connection(self):
        for _ in range(3):
            self.http.json("GET", self.base + "/a")
        self.assertEqual(KeepAliveHandler.connections, 1)
        self.assertEqual(self.http.count, 3)

    def test_a_connection_the_server_dropped_costs_nothing(self):
        self.http.json("GET", self.base + "/drop")
        self.assertEqual(self.http.json("GET", self.base + "/a"), {})
        self.assertEqual(KeepAliveHandler.connections, 2)
        self.assertEqual(self.http.count, 2)

    def test_a_write_never_goes_out_on_an_old_connection(self):
        self.http.json("GET", self.base + "/drop")
        self.http.json("POST", self.base + "/write", body={})
        self.assertEqual(KeepAliveHandler.seen.count(("POST", "/write")), 1)
        self.assertEqual(KeepAliveHandler.connections, 2)

    def test_a_connection_idle_too_long_is_not_trusted(self):
        self.http.json("GET", self.base + "/a")
        with mock.patch.object(_http, "_IDLE_MAX", 0):
            self.http.json("GET", self.base + "/a")
        self.assertEqual(KeepAliveHandler.connections, 2)

    def test_threads_do_not_share_a_connection_at_once(self):
        results = []

        def work():
            for _ in range(10):
                results.append(self.http.json("GET", self.base + "/a"))

        threads = [threading.Thread(target=work) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(results, [{}] * 80)
        self.assertEqual(self.http.count, 80)


if __name__ == "__main__":
    unittest.main()
