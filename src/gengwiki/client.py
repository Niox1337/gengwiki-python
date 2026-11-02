"""The client. Every read goes local first, the network is the fallback."""

import logging
import os
import threading
import urllib.parse
import uuid
from pathlib import Path
from typing import Any, Callable, Sequence

from . import _search
from ._http import Http, check_url
from ._keyring import Keyring
from ._store import Hit, Store, namespace
from .errors import AccountApiUnavailable, AuthError, ForbiddenError, NotFoundError, UnavailableError
from .keys import Keys
from .models import Lexicon, LexiconEntry, Meme, MemeSummary, Persona, RateLimit, Sticker, StickerPack

log = logging.getLogger("gengwiki")

DEFAULT_API_URL = "https://api.gengwiki.niox.lol"
DEFAULT_SITE_URL = "https://gengwiki.niox.lol"

# The API returns at most this many rows and has no paging. Fewer rows than this means the list is complete.
LIST_MAX = 100

# Seconds. A key's scope is fixed when it is created, so its list only changes when a meme is edited or hidden.
TTL_LIST = 6 * 3600
TTL_TRENDING = 15 * 60
TTL_LEXICON = 3600
TTL_MISSING = 3600
# Personas have no edit route, only publish and unpublish.
TTL_PERSONA = 7 * 86400
TTL_CATALOG = 86400
# The persona catalog returns at most this many rows, backend/src/personas.rs.
PERSONA_LIST_MAX = 60

_SHARED = "shared"  # data that is the same for every key
_MISSING = {"__missing__": True}
_IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}


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
        if not self._key:
            saved = self._keyring.read()
            self._key = saved["keys"].get(saved.get("current"), {}).get("key")
        self.keys = Keys(self)

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
        return namespace(self._key)

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

    def _persona_row(self, key: str) -> dict:
        return self._cached(namespace(key), "persona", f"{self.base_url}/v1/persona", TTL_PERSONA, token=key, missing_ttl=TTL_CATALOG)

    def persona(self) -> Persona | None:
        """The persona bound to the current key, or None if it has none."""
        try:
            return Persona.of(self._persona_row(self._token()))
        except NotFoundError:
            return None

    def use_persona(self, persona: str) -> Persona:
        """Switch to a persona by title or id. A key binds one persona for life, so switching means switching keys.

        A saved key bound to it is used at once, with no request once its persona has been read. With no such key
        and a login, one is created and saved, the same way the website does it.
        """
        name = self.keys._name_for_persona(persona)
        if name is None:
            if not self.keys.logged_in:
                known = sorted(k.persona_title for k in self.keys.local() if k.persona_title)
                raise NotFoundError(
                    f"no saved key is bound to persona {persona!r}, saved personas are {known}. "
                    "Save a key with keys.add(), or log in with keys.login() to create one",
                    404,
                    "not_found",
                )
            row = self._catalog_row(persona)
            name = self.keys.create(row["title"], persona=row["id"]).name
        row = self._persona_row(self.keys.secret(name))  # read before switching, so a failure leaves the old persona on
        self.keys.use(name)
        return Persona.of(row)

    def personas(self, q: str = "") -> list[Persona]:
        """Published personas to pick from. Where the site hides the catalog, the ones the saved keys are bound to."""
        q = q.strip()
        url = f"{self.site_url}/api/personas"
        try:
            rows = self._cached(_SHARED, "personas", url, TTL_CATALOG, token=None)
            if q and len(rows) >= PERSONA_LIST_MAX:
                # The list is cut off, so only the server can search the rest.
                return [Persona.of(r) for r in self._cached(_SHARED, f"personas:{q.lower()}", url, TTL_CATALOG, token=None, params={"q": q})]
        except NotFoundError:
            rows = [{"id": k.persona_id, "title": k.persona_title} for k in self.keys.local() if k.persona_id]
        return [Persona.of(r) for r in _search.search_personas(q, rows)]

    def _catalog_row(self, wanted: str) -> dict:
        """One persona from the catalog with its memes and packs, by exact id or title."""
        url = f"{self.site_url}/api/personas"
        try:
            rows = self._cached(_SHARED, "personas", url, TTL_CATALOG, token=None)
            if len(rows) >= PERSONA_LIST_MAX:
                rows = self._cached(_SHARED, f"personas:{wanted.lower()}", url, TTL_CATALOG, token=None, params={"q": wanted})
        except NotFoundError as e:
            raise AccountApiUnavailable(f"{self.site_url} does not expose the persona catalog") from e
        row = next((r for r in rows if wanted == r["id"] or wanted.casefold() == r["title"].casefold()), None)
        if row is None:
            raise NotFoundError(f"no published persona {wanted!r}", 404, "not_found")
        return row

    # ---------- stickers ----------

    def _packs(self) -> list[dict]:
        return self._v1("packs", "/sticker-packs", TTL_LIST)

    def sticker_packs(self) -> list[StickerPack]:
        return [StickerPack.of(p) for p in self._packs()]

    def search_stickers(self, q: str = "", limit: int = 20) -> list[Sticker]:
        """Search this key's stickers by caption, pack title or pack tag. The pack list is never cut off, so this is always local."""
        return [Sticker.of(s) for s in _search.search_stickers(q, self._packs(), max(1, limit))]

    def sticker_image(self, sticker_id: str) -> Path:
        """Path of the image on disk, downloaded once. Images never change and the site has a daily image budget."""
        sid = str(uuid.UUID(sticker_id))  # it names a file, so it must really be a uuid
        folder = self.home / "stickers"
        for found in folder.glob(f"{sid}.*"):
            return found
        with self._lock:
            for found in folder.glob(f"{sid}.*"):
                return found
            # The image route takes no key and does not count against one.
            body, headers = self._http.request("GET", f"{self.base_url}/v1/stickers/{sid}/image", retries=1)
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / (sid + _IMAGE_TYPES.get(headers.get_content_type(), ".img"))
            tmp = folder / f".{sid}.tmp"
            tmp.write_bytes(body)
            os.replace(tmp, path)
            return path

    # ---------- lexicons ----------

    def _lexicons(self) -> list[dict]:
        return self._v1("lexicons", "/me/lexicons", TTL_LEXICON)

    def _entries(self, lexicon_id: str) -> list[dict]:
        path = f"/me/lexicons/{urllib.parse.quote(lexicon_id, safe='')}/entries"
        return self._v1(f"entries:{lexicon_id}", path, TTL_LEXICON)

    def lexicons(self) -> list[Lexicon]:
        return [Lexicon.of(x) for x in self._lexicons()]

    def lexicon_entries(self, lexicon_id: str) -> list[LexiconEntry]:
        return [LexiconEntry.of(x) for x in self._entries(lexicon_id)]

    def search_lexicons(self, q: str = "", limit: int = 20) -> list[LexiconEntry]:
        """Search the entries of all my lexicons. The first call reads each lexicon once."""
        rows = [e for lex in self._lexicons() for e in self._entries(lex["id"])]
        return [LexiconEntry.of(e) for e in _search.search_entries(q, rows, max(1, limit))]

    def _post(self, path: str, body: dict) -> dict:
        return self._http.json("POST", f"{self.base_url}/v1{path}", token=self._token(), body=body)

    def _patch_cached(self, key: str, change: Callable[[list], list]) -> None:
        """Apply a write we just made to the cached list, so writing does not force a re-read."""
        hit = self._store.get(self._ns, key)
        if hit and hit.value != _MISSING:
            self._store.put(self._ns, key, change(hit.value))

    def create_lexicon(self, name: str, description: str = "") -> Lexicon:
        row = self._post("/me/lexicons", {"name": name, "description": description})
        self._patch_cached("lexicons", lambda rows: [*rows, row])
        return Lexicon.of(row)

    def add_lexicon_entry(
        self, lexicon_id: str, term: str, *, aliases: Sequence[str] = (), note: str = "", tags: Sequence[str] = ()
    ) -> LexiconEntry:
        path = f"/me/lexicons/{urllib.parse.quote(lexicon_id, safe='')}/entries"
        row = self._post(path, {"term": term, "aliases": list(aliases), "note": note, "tags": list(tags)})
        self._patch_cached(f"entries:{lexicon_id}", lambda rows: [*rows, row])
        self._patch_cached("lexicons", lambda rows: [{**x, "entries": x["entries"] + (x["id"] == lexicon_id)} for x in rows])
        return LexiconEntry.of(row)

    # ---------- usage, always live ----------

    def usage(self) -> dict:
        """Requests per day over the last 30 days, as the server counted them."""
        return self._http.json("GET", f"{self.base_url}/v1/me/usage", token=self._token(), retries=1)

    def rate_limit(self) -> RateLimit:
        return RateLimit.of(self._http.json("GET", f"{self.base_url}/v1/me/rate-limit", token=self._token(), retries=1))

    # ---------- offline ----------

    def sync(self, *, images: bool = False) -> dict[str, int]:
        """Download everything this key can see, so later calls need no network.

        Costs one request per meme the first time and nothing when run again. An interrupted sync resumes where it stopped.
        """
        before = self.request_count
        summary = {"memes": 0, "stickers": 0, "images": 0}

        def allowed(step: Callable[[], Any], default: Any = None) -> Any:
            # A key without the scope simply has nothing to sync there.
            try:
                return step()
            except ForbiddenError:
                return default

        for row in allowed(self._list, []):
            self.meme(row["slug"])
            summary["memes"] += 1
        allowed(self.persona)
        allowed(self.trending)
        for pack in allowed(self.sticker_packs, []):
            for sticker in pack.stickers:
                summary["stickers"] += 1
                if images:
                    self.sticker_image(sticker.id)
                    summary["images"] += 1
        allowed(self.search_lexicons)
        summary["requests"] = self.request_count - before
        return summary
