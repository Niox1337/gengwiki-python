"""API keys. Saved keys work with no login, creating and rotating go through the account API."""

import time
import urllib.parse
from typing import TYPE_CHECKING, Any, Sequence

from ._store import namespace
from .errors import AccountApiUnavailable, AuthError, ForbiddenError, GengWikiError, NotFoundError, UnavailableError
from .models import ApiKey, LocalKey

if TYPE_CHECKING:
    from .client import GengWiki

_PREFIX_LEN = len("gwk_live_") + 6  # what the server stores in the clear, common::generate_api_key


class Keys:
    def __init__(self, client: "GengWiki"):
        self._c = client
        self._ring = client._keyring

    # ---------- saved on this machine, no request ----------

    def add(self, name: str, key: str) -> LocalKey:
        """Save a key made on the website. The first key saved becomes the current one."""
        if not key.startswith("gwk_"):
            raise ValueError("an API key starts with gwk_")
        with self._ring.edit() as data:
            if data["keys"].get(name, {}).get("key", key) != key:
                raise ValueError(f"a different key is already saved as {name!r}")
            data["keys"].setdefault(name, {"key": key})
            first = "current" not in data
            if first:
                data["current"] = name
        if first and not self._c._key:
            self._c._key = key
        return self._local(name)

    def local(self) -> list[LocalKey]:
        return [self._local(name) for name in self._ring.read()["keys"]]

    def _local(self, name: str) -> LocalKey:
        e = self._ring.read()["keys"][name]
        return LocalKey(
            name=name,
            prefix=e["key"][:_PREFIX_LEN],
            id=e.get("id"),
            persona_id=e.get("persona_id"),
            persona_title=e.get("persona_title"),
            current=e["key"] == self._c._key,
        )

    def secret(self, name: str) -> str:
        """The key itself, for handing to another program."""
        e = self._ring.read()["keys"].get(name)
        if e is None:
            raise NotFoundError(f"no key saved as {name!r}", 404, "not_found")
        return e["key"]

    def use(self, name: str) -> LocalKey:
        """Switch this client to a saved key, and make it the default for new clients."""
        with self._ring.edit() as data:
            if name not in data["keys"]:
                raise NotFoundError(f"no key saved as {name!r}", 404, "not_found")
            data["current"] = name
            self._c._key = data["keys"][name]["key"]
        return self._local(name)

    def remove(self, name: str) -> None:
        """Forget a key on this machine. It keeps working on the server, revoke() ends it there."""
        with self._ring.edit() as data:
            e = data["keys"].pop(name, None)
            if data.get("current") == name:
                del data["current"]
        if e:
            self._c._store.drop(namespace(e["key"]))
            if self._c._key == e["key"]:
                self._c._key = None

    # ---------- personas ----------

    def persona_row(self, name: str) -> dict | None:
        """What the server says about the persona of a saved key, remembered in the keyring."""
        key = self._ring.read()["keys"][name]["key"]
        try:
            row = self._c._persona_row(key)
        except (NotFoundError, ForbiddenError):
            row = None  # a key's persona and scopes are fixed at creation, so this answer lasts
        with self._ring.edit() as data:
            data["keys"][name]["persona_id"] = row["id"] if row else None
            data["keys"][name]["persona_title"] = row["title"] if row else None
        return row

    def _name_for_persona(self, wanted: str) -> str | None:
        """The saved key bound to this persona. Only asks the server about keys it has never seen."""
        keys = self._ring.read()["keys"]

        def matches(pid: str | None, title: str | None) -> bool:
            return wanted == pid or (title is not None and wanted.casefold() == title.casefold())

        for name, e in keys.items():
            if matches(e.get("persona_id"), e.get("persona_title")):
                return name
        for name, e in keys.items():
            if "persona_id" in e:
                continue
            try:
                row = self.persona_row(name)
            except GengWikiError:
                continue  # revoked or the server is down, this key cannot answer now
            if row and matches(row["id"], row["title"]):
                return name
        return None

    # ---------- account API ----------

    def login(self, email: str, password: str) -> dict:
        """Log in to manage keys. The password is not kept, only a token that lasts seven days."""
        r = self._account("POST", "/auth/login", {"email": email, "password": password}, None, dict)
        with self._ring.edit() as data:
            data["session"] = {"token": r["token"], "expires_at": time.time() + r["expires_in"]}
        return r["user"]

    def logout(self) -> None:
        with self._ring.edit() as data:
            data.pop("session", None)

    @property
    def logged_in(self) -> bool:
        s = self._ring.read().get("session")
        return bool(s) and s["expires_at"] > time.time()

    def _account(self, method: str, path: str, body: dict | None, token: str | None, expect: type | None = None) -> Any:
        try:
            return self._c._http.json(method, f"{self._c.site_url}/api{path}", token=token, body=body, expect=expect)
        except UnavailableError:
            raise
        except GengWikiError as e:
            # A real answer from the backend always has an error code, anything else came from the website in front.
            if e.code is None:
                raise AccountApiUnavailable(
                    f"{self._c.site_url} does not expose the account API. Create keys on the website and save them with keys.add()"
                ) from e
            raise

    def _session(self, method: str, path: str, body: dict | None = None, expect: type | None = dict) -> Any:
        if not self.logged_in:
            raise AuthError("not logged in. Call client.keys.login(email, password) first", code="unauthorized")
        try:
            return self._account(method, path, body, self._ring.read()["session"]["token"], expect)
        except AuthError:
            self.logout()
            raise

    def list(self, *, include_revoked: bool = False) -> list[ApiKey]:
        """All keys on the account, as the server sees them. Always live, this is rare and must be accurate."""
        rows = [ApiKey.of(r) for r in self._session("GET", "/me/keys", expect=list)]
        return rows if include_revoked else [r for r in rows if not r.revoked_at]

    def create(
        self,
        name: str,
        *,
        persona: str | None = None,
        memes: Sequence[str] = (),
        packs: Sequence[str] = (),
        people: Sequence[str] = (),
        scopes: Sequence[str] | None = None,
    ) -> LocalKey:
        """Create a key and save it here, since the server shows the secret only this once.

        As on the website, picking a persona (by title or id) also brings in its memes, sticker packs and people.
        """
        memes, packs, people = list(memes), list(packs), list(people)
        persona_id = None
        if persona:
            row = self._c._catalog_row(persona)
            persona_id = row["id"]
            memes = list(dict.fromkeys([*memes, *(m["slug"] for m in row["memes"])]))
            packs = list(dict.fromkeys([*packs, *(p["id"] for p in row["packs"])]))
            people = list(dict.fromkeys([*people, *(p["id"] for p in row.get("people", []))]))
        body: dict[str, Any] = {"name": name, "memes": memes, "packs": packs, "people": people, "persona": persona_id}
        if scopes is not None:
            body["scopes"] = list(scopes)
        return self._save(self._session("POST", "/me/keys", body))

    def _save(self, created: dict, name: str | None = None) -> LocalKey:
        row = created["api_key"]
        with self._ring.edit() as data:
            if name is None:
                name = row["name"]
                if name in data["keys"]:
                    # Names repeat on the server but not here, and this secret must not be lost.
                    name = f"{name}-{row['prefix'][-6:]}"
            persona = row.get("persona") or {}
            data["keys"][name] = {
                "key": created["key"],
                "id": row["id"],
                "persona_id": persona.get("id"),
                "persona_title": persona.get("title"),
            }
            data.setdefault("current", name)
        if not self._c._key:
            self._c._key = created["key"]
        return self._local(name)

    def _resolve(self, ref: str) -> tuple[str, str | None, str | None]:
        """A saved name, a remote name or an id, as (id, saved name, the secret if we hold it)."""
        keys = self._ring.read()["keys"]
        saved = keys.get(ref)
        if saved and saved.get("id"):
            return saved["id"], ref, saved["key"]
        rows = self.list()
        if saved:
            found = [r for r in rows if r.prefix == saved["key"][:_PREFIX_LEN]]
        else:
            found = [r for r in rows if ref in (r.id, r.name)]
        if not found:
            raise NotFoundError(f"no active key {ref!r} on this account", 404, "not_found")
        if len(found) > 1:
            raise ValueError(f"{len(found)} keys are named {ref!r}, use the id")
        prefix = found[0].prefix
        local = next((n for n, e in keys.items() if e["key"][:_PREFIX_LEN] == prefix), None)
        if local:
            return found[0].id, local, keys[local]["key"]
        mine = self._c._key if self._c._key and self._c._key[:_PREFIX_LEN] == prefix else None
        return found[0].id, None, mine

    def rotate(self, ref: str) -> LocalKey:
        """New secret, same name and scope. The local cache moves over, so rotating costs no re-download."""
        key_id, local, old = self._resolve(ref)
        created = self._session("POST", f"/me/keys/{urllib.parse.quote(key_id, safe='')}/rotate")
        if old and self._c._key == old:
            self._c._key = created["key"]
        saved = self._save(created, local)
        if old:
            self._c._store.rename(namespace(old), namespace(created["key"]))
        return saved

    def revoke(self, ref: str) -> None:
        """End a key on the server and forget it here."""
        key_id, local, secret = self._resolve(ref)
        self._session("DELETE", f"/me/keys/{urllib.parse.quote(key_id, safe='')}", expect=None)
        if local:
            self.remove(local)
        if secret:
            self._c._store.drop(namespace(secret))
            if self._c._key == secret:
                self._c._key = None
