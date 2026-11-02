import gzip
import http.server
import json
import threading
import unittest

from gengwiki._http import Http, check_url
from gengwiki.errors import AuthError, GengWikiError, NetworkError, RateLimitError, ServerError


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


if __name__ == "__main__":
    unittest.main()
