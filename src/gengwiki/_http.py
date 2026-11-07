"""Stdlib HTTP with typed errors. Knows nothing about caching."""

import email.message
import gzip
import http.client
import ipaddress
import json
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from typing import Any

from . import __version__
from .errors import (
    AuthError,
    BadRequestError,
    BadResponseError,
    ConflictError,
    ForbiddenError,
    GengWikiError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServerError,
    UnavailableError,
)

_BY_STATUS = {400: BadRequestError, 401: AuthError, 403: ForbiddenError, 404: NotFoundError, 409: ConflictError}
# Seconds an idle connection is trusted. A firewall can drop one without a word, and the next request would hang until the timeout.
_IDLE_MAX = 30
RETRY_WAIT = 0.5  # doubles each try


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib would forward the Authorization header to wherever a redirect points."""

    def redirect_request(self, *args, **kwargs):
        return None


def check_url(url: str) -> str:
    """Bearer tokens only travel over HTTPS, plain HTTP is for a dev server on this machine."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme == "https" and parts.hostname:
        return url.rstrip("/")
    if parts.scheme == "http" and parts.hostname:
        try:
            loopback = ipaddress.ip_address(parts.hostname).is_loopback
        except ValueError:
            loopback = parts.hostname == "localhost"
        if loopback:
            return url.rstrip("/")
    raise ValueError(f"{url!r} must be https, or http on localhost")


def _raise_for(status: int, body: bytes, headers: email.message.Message) -> None:
    code, message = None, f"HTTP {status}"
    try:
        err = json.loads(body)["error"]
        code, message = err["code"], err["message"]
    except (ValueError, KeyError, TypeError):
        pass
    if status == 429:
        try:
            retry_after = float(headers.get("Retry-After", 0))
        except ValueError:
            retry_after = 0
        raise RateLimitError(message, retry_after=retry_after)
    if status >= 500:
        raise ServerError(message, status, code)
    raise _BY_STATUS.get(status, GengWikiError)(message, status, code)


def _fits(value: Any, shape: Any) -> bool:
    """shape is a type, [shape of every row], or {field: shape} for the fields that must be there. Other fields are ignored."""
    if isinstance(shape, list):
        return isinstance(value, list) and all(_fits(row, shape[0]) for row in value)
    if isinstance(shape, dict):
        return isinstance(value, dict) and all(k in value and _fits(value[k], s) for k, s in shape.items())
    return isinstance(value, shape)


class Http:
    def __init__(self, timeout: float = 15):
        self.timeout = timeout
        self.count = 0
        self._opener = urllib.request.build_opener(_NoRedirect)
        self._proxies = urllib.request.getproxies()
        self._idle: dict[tuple[str, str], list[tuple[http.client.HTTPConnection, float]]] = {}
        self._lock = threading.Lock()

    def close(self) -> None:
        with self._lock:
            idle, self._idle = self._idle, {}
        for conns in idle.values():
            for conn, _ in conns:
                conn.close()

    def _checkout(self, req: urllib.request.Request) -> tuple[http.client.HTTPConnection, bool]:
        """An idle connection and True, or a new one and False. Only a GET reuses one, since a failure on a reused connection is sent again."""
        if req.get_method() == "GET":
            with self._lock:
                idle = self._idle.get((req.type, req.host), [])
                while idle:
                    conn, since = idle.pop()
                    if time.monotonic() - since < _IDLE_MAX:
                        return conn, True
                    conn.close()
        cls = http.client.HTTPSConnection if req.type == "https" else http.client.HTTPConnection
        return cls(req.host, timeout=self.timeout), False

    def _exchange(self, req: urllib.request.Request) -> tuple[int, bytes, email.message.Message]:
        if req.type in self._proxies and not urllib.request.proxy_bypass(req.host):
            # http.client knows nothing of proxies, urllib reads them from the system.
            try:
                with self._opener.open(req, timeout=self.timeout) as res:
                    return res.status, res.read(), res.headers
            except urllib.error.HTTPError as e:
                with e:
                    return e.code, e.read(), e.headers
        while True:
            conn, reused = self._checkout(req)
            try:
                conn.request(req.get_method(), req.selector, req.data, dict(req.header_items()))
                res = conn.getresponse()
                body = res.read()
            except Exception as e:
                conn.close()
                # The server closed it while it sat idle, which says nothing about the service.
                if reused and isinstance(e, (ConnectionError, ssl.SSLError)):
                    continue
                raise
            if conn.sock:  # the server may have said it closes after this response
                with self._lock:
                    self._idle.setdefault((req.type, req.host), []).append((conn, time.monotonic()))
            return res.status, body, res.headers

    def _once(self, req: urllib.request.Request) -> tuple[bytes, email.message.Message]:
        with self._lock:
            self.count += 1
        try:
            status, body, headers = self._exchange(req)
            if not 200 <= status < 300:
                _raise_for(status, body, headers)
            if headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            return body, headers
        # A connection cut mid-response or a damaged body is the same outage to the caller.
        except (OSError, EOFError, http.client.HTTPException, zlib.error) as e:
            raise NetworkError(f"cannot reach {req.host}: {e!r}") from e

    def request(
        self,
        method: str,
        url: str,
        *,
        token: str | None = None,
        params: dict | None = None,
        body: dict | bytes | None = None,
        retries: int = 0,
    ) -> tuple[bytes, email.message.Message]:
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {"User-Agent": f"gengwiki-python/{__version__}", "Accept-Encoding": "gzip"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = None
        if isinstance(body, bytes):
            data = body
            headers["Content-Type"] = "application/octet-stream"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        for attempt in range(retries + 1):
            try:
                return self._once(req)
            except UnavailableError as e:
                # A long Retry-After is the daily limit, waiting it out would hang the caller.
                wait = e.retry_after if isinstance(e, RateLimitError) else RETRY_WAIT * 2**attempt
                if attempt == retries or wait > 5:
                    raise
                time.sleep(wait)
        raise AssertionError("unreachable")

    def json(self, method: str, url: str, *, expect: Any = None, **kwargs):
        """The decoded body. With expect, anything but that shape is a bad response, so it never reaches the cache."""
        body, headers = self.request(method, url, **kwargs)
        try:
            value = json.loads(body) if body else None
        except ValueError as e:
            raise BadResponseError(f"expected JSON from {url}, got {headers.get_content_type()}", code="bad_response") from e
        if expect and not _fits(value, expect):
            raise BadResponseError(f"unexpected JSON from {url}", code="bad_response")
        return value
