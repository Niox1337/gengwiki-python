"""The client. Every read goes local first, the network is the fallback."""

import hashlib
import logging
import os
import threading
import urllib.parse
from pathlib import Path
from typing import Any, Callable

from . import _search
from ._http import Http, check_url
from ._keyring import Keyring
from ._store import Hit, Store
from .errors import AuthError, NotFoundError, UnavailableError
from .models import Meme, MemeSummary, Persona

log = logging.getLogger("gengwiki")

DEFAULT_API_URL = "https://api.gengwiki.niox.lol"
DEFAULT_SITE_URL = "https://gengwiki.niox.lol"

# The API returns at most this many rows and has no paging. Fewer rows than this means the list is complete.
LIST_MAX = 100

# Seconds. A key's scope is fixed when it is created, so its list only changes when a meme is edited or hidden.
TTL_LIST = 6 * 3600
TTL_TRENDING = 15 * 60
TTL_MISSING = 3600
# Personas have no edit route, only publish and unpublish.
TTL_PERSONA = 7 * 86400

_SHARED = "shared"  # data that is the same for every key
_MISSING = {"__missing__": True}


class GengWiki:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str | None = None,
        site_url: str | None = None,
        home: str | os.PathLike | None = None,
        timeout: float = 15,
    ):
        self.base_url = check_url(base_url or os.environ.get("GENGWIKI_API_URL") or DEFAULT_API_URL)
        self.site_url = check_url(site_url or os.environ.get("GENGWIKI_SITE_URL") or DEFAULT_SITE_URL)
        # One folder per API host, so a key saved for one host is never sent to another.
        host = urllib.parse.urlsplit(self.base_url).netloc.replace(":", "_")
        self.home = Path(home or os.environ.get("GENGWIKI_HOME") or Path.home() / ".gengwiki") / host
        try:
            self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        except OSError as e:
            log.warning("cannot create %s, caching in memory only: %s", self.home, e)
        self._http = Http(timeout)
        self._store = Store(self.home / "cache.sqlite3")
        self._keyring = Keyring(self.home / "keys.json")
        self._lock = threading.Lock()
        self._key = api_key or os.environ.get("GENGWIKI_API_KEY")

    def close(self) -> None:
        self._store.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def request_count(self) -> int:
        """Requests this client has actually sent. Handy for seeing what the cache saves."""
        return self._http.count

    @property
    def _ns(self) -> str:
        return _namespace(self._key)

    def refresh(self) -> None:
        """Make the next read of everything go to the network. The old data stays as a fallback."""
        self._store.expire(self._ns)
        self._store.expire(_SHARED)

    def _cached(
        self,
        ns: str,
        key: str,
        url: str,
        ttl: float,
        *,
        token: str | None,
        params: dict | None = None,
        valid: Callable[[Any], bool] | None = None,
        missing_ttl: float = TTL_MISSING,
    ) -> Any:
        """Return the local copy if it is good, otherwise fetch it. An outage serves the old copy instead of failing."""

        def good(hit: Hit | None) -> bool:
            if hit is None:
                return False
            if hit.value == _MISSING:
                return hit.age < missing_ttl
            return valid(hit.value) if valid else hit.age < ttl

        def answer(hit: Hit) -> Any:
            if hit.value == _MISSING:
                raise NotFoundError("resource not found", 404, "not_found")
            return hit.value

        hit = self._store.get(ns, key)
        if good(hit):
            return answer(hit)
        # ponytail: one lock over all misses, so parallel tool calls share a fetch and cache hits never wait.
        # Per-key locks if unrelated misses ever queue up noticeably.
        with self._lock:
            hit = self._store.get(ns, key)
            if good(hit):
                return answer(hit)
            usable = hit is not None and hit.value != _MISSING
            try:
                # With an old copy in hand a retry only delays the answer.
                value = self._http.json("GET", url, token=token, params=params, retries=0 if usable else 1)
            except NotFoundError:
                self._store.put(ns, key, _MISSING)
                raise
            except UnavailableError as e:
                if usable:
                    log.warning("serving a stale copy of %s: %s", url, e)
                    return hit.value
                raise
            self._store.put(ns, key, value)
            return value

    def _token(self) -> str:
        if not self._key:
            raise AuthError("no API key. Pass api_key, set GENGWIKI_API_KEY, or save one with client.keys.add()", code="unauthorized")
        return self._key

    def _v1(self, key: str, path: str, ttl: float, *, shared: bool = False, **kwargs) -> Any:
        return self._cached(_SHARED if shared else self._ns, key, f"{self.base_url}/v1{path}", ttl, token=self._token(), **kwargs)

    # ---------- memes ----------

    def _list(self) -> list[dict]:
        """Everything this key can see, up to LIST_MAX. Searches and detail lookups all lean on this one request."""
        return self._v1("list", "/memes/search", TTL_LIST, params={"q": "", "limit": LIST_MAX})

    def search_memes(self, q: str = "", limit: int = 20) -> list[MemeSummary]:
        """Search this key's memes. An empty q lists them by heat."""
        limit = max(1, min(limit, LIST_MAX))
        rows = self._list()
        if len(rows) < LIST_MAX or not q.strip():
            return [MemeSummary.of(r) for r in _search.search_memes(q, rows, limit)]
        # The list is cut off, so only the server can search the rest.
        q = q.strip()
        rows = self._v1(f"search:{q.lower()}", "/memes/search", TTL_LIST, params={"q": q, "limit": LIST_MAX})
        return [MemeSummary.of(r) for r in rows[:limit]]

    def meme(self, slug: str) -> Meme:
        """One meme with its full text. Takes a slug, or an exact title or alias."""
        rows = self._list()
        wanted = slug.strip().lower()
        row = next((r for r in rows if r["slug"] == slug), None) or next(
            (r for r in rows if wanted in (s.lower() for s in [r["title"], *r["aliases"]])), None
        )
        if row is None:
            if len(rows) < LIST_MAX:
                raise NotFoundError(f"{slug!r} is not among this key's memes", 404, "not_found")
            # Past the end of the list. Only the server knows whether this key may read it, so cache it per key.
            path = f"/memes/{urllib.parse.quote(slug, safe='')}"
            return Meme.of(self._v1(f"meme:{slug}", path, TTL_LIST))
        # The list proved this key may read it, so the text can be shared between keys.
        # The list's updated_at says whether the copy is current, which saves one request per meme.
        updated_at = row["updated_at"]
        path = f"/memes/{urllib.parse.quote(row['slug'], safe='')}"
        return Meme.of(self._v1(f"meme:{row['slug']}", path, 0, shared=True, valid=lambda m: m.get("updated_at") == updated_at))

    def trending(self, tag: str = "", limit: int = 20) -> list[MemeSummary]:
        """The hot board, site-wide or for one tag. Not limited by the key's scope, so all keys share one copy."""
        # Always the full board, so a different limit later is not another request.
        rows = self._v1(f"trending:{tag}", "/trending", TTL_TRENDING, shared=True, params={"tag": tag, "limit": LIST_MAX})
        return [MemeSummary.of(r) for r in rows[: max(1, min(limit, LIST_MAX))]]

    # ---------- persona ----------

    def persona(self) -> Persona | None:
        """The persona bound to the current key, or None if it has none."""
        try:
            return Persona.of(self._v1("persona", "/persona", TTL_PERSONA, missing_ttl=86400))
        except NotFoundError:
            return None


def _namespace(key: str | None) -> str:
    """Cache rows are filed under a hash, the key itself never reaches the cache."""
    return hashlib.sha256((key or "").encode()).hexdigest()[:16]
