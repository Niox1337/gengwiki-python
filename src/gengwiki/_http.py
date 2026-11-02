"""Stdlib HTTP with typed errors. Knows nothing about caching."""

import email.message
import gzip
import ipaddress
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import __version__
from .errors import (
    AuthError,
    BadRequestError,
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


class Http:
    def __init__(self, timeout: float = 15):
        self.timeout = timeout
        self.count = 0
        self._opener = urllib.request.build_opener(_NoRedirect)

    # ponytail: urllib opens one connection per request. Requests are rare by design, pool with http.client if that changes.
    def _once(self, req: urllib.request.Request) -> tuple[bytes, email.message.Message]:
        self.count += 1
        try:
            with self._opener.open(req, timeout=self.timeout) as res:
                body, headers = res.read(), res.headers
        except urllib.error.HTTPError as e:
            with e:
                _raise_for(e.code, e.read(), e.headers)
            raise  # unreachable, _raise_for always raises
        except (OSError, EOFError) as e:
            raise NetworkError(f"cannot reach {req.host}: {e}") from e
        if headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        return body, headers

    def request(
        self,
        method: str,
        url: str,
        *,
        token: str | None = None,
        params: dict | None = None,
        body: dict | None = None,
        retries: int = 0,
    ) -> tuple[bytes, email.message.Message]:
        if params:
            url += "?" + urllib.parse.urlencode(params)
        headers = {"User-Agent": f"gengwiki-python/{__version__}", "Accept-Encoding": "gzip"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        for attempt in range(retries + 1):
            try:
                return self._once(req)
            except UnavailableError as e:
                # A long Retry-After is the daily limit, waiting it out would hang the caller.
                wait = e.retry_after if isinstance(e, RateLimitError) else 0.5 * 2**attempt
                if attempt == retries or wait > 5:
                    raise
                time.sleep(wait)
        raise AssertionError("unreachable")

    def json(self, method: str, url: str, **kwargs):
        body, _ = self.request(method, url, **kwargs)
        return json.loads(body) if body else None
