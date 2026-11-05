"""Saved API keys, the login token and subscribed tags, in one JSON file only this user can read.

With the keychain extra installed the secrets go to the OS keychain, and the file keeps only a ref to each.
"""

import contextlib
import copy
import errno
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Iterator

from .errors import GengWikiError

log = logging.getLogger("gengwiki")

if os.name == "nt":
    import msvcrt

    def _lock(fd: int) -> None:
        while True:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return
            except OSError as e:
                if e.errno not in (errno.EACCES, errno.EDEADLOCK):
                    raise
                time.sleep(0.02)

    def _unlock(fd: int) -> None:
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX)

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


def _keychain() -> Any:
    try:
        import keyring
    except ImportError:
        return None
    return keyring


def _patiently(call: Callable[[], Any]) -> Any:
    """On Windows a file being read or replaced refuses the other side for a moment."""
    for _ in range(50 if os.name == "nt" else 0):
        try:
            return call()
        except PermissionError:
            time.sleep(0.02)
    return call()


class Keyring:
    def __init__(self, path: Path):
        self.path = path
        self._service = f"gengwiki:{path.resolve()}"
        self._known: dict[str, str] = {}  # a new secret always gets a new ref, so this can never go stale

    @staticmethod
    def _holders(data: dict) -> Iterator[tuple[dict, str]]:
        for entry in data["keys"].values():
            yield entry, "key"
        if data.get("session"):
            yield data["session"], "token"

    def _fetch(self, ref: str) -> str:
        if ref not in self._known:
            keychain = _keychain()
            try:
                secret = keychain.get_password(self._service, ref) if keychain else None
            except Exception as e:  # each backend has its own errors
                raise GengWikiError(f"cannot read a secret of {self.path} from the OS keychain: {e}") from e
            if secret is None:
                raise GengWikiError(
                    f"{self.path} keeps a secret in the OS keychain that cannot be found. "
                    "Install gengwiki[keychain] if it is missing, otherwise delete the file and save your keys again"
                )
            self._known[ref] = secret
        return self._known[ref]

    def read(self) -> dict:
        try:
            data = json.loads(_patiently(lambda: self.path.read_text("utf-8")))
        except FileNotFoundError:
            data = {}
        except ValueError as e:
            # Secrets may be in there and are shown only once, so never overwrite this file.
            raise GengWikiError(f"{self.path} is not valid JSON, fix or delete it: {e}") from e
        data.setdefault("keys", {})
        for holder, field in self._holders(data):
            if "ref" in holder:
                holder[field] = self._fetch(holder["ref"])
        return data

    def _stored(self, data: dict) -> dict:
        """What goes in the file. A secret stays in the file if the keychain refuses it, since it is shown only once."""
        stored = copy.deepcopy(data)
        keychain = _keychain()
        for holder, field in self._holders(stored):
            secret = holder[field]
            if self._known.get(holder.get("ref")) == secret:
                del holder[field]
                continue
            holder.pop("ref", None)
            if keychain:
                ref = uuid.uuid4().hex
                try:
                    keychain.set_password(self._service, ref, secret)
                except Exception as e:  # each backend has its own errors
                    log.warning("the OS keychain refused a secret, keeping it in %s: %s", self.path, e)
                    continue
                self._known[ref] = secret
                holder["ref"] = ref
                del holder[field]
        return stored

    def _forget(self, refs: set[str]) -> None:
        keychain = _keychain()
        for ref in refs:
            self._known.pop(ref, None)
            try:
                if keychain:
                    keychain.delete_password(self._service, ref)
            except Exception as e:  # each backend has its own errors
                log.warning("cannot delete an old secret of %s from the OS keychain: %s", self.path, e)

    @contextlib.contextmanager
    def _exclusive(self) -> Iterator[None]:
        """Across read, change and write, so threads and processes saving at once all keep their edit."""
        fd = os.open(self.path.with_name(self.path.name + ".lock"), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            _lock(fd)
            try:
                yield
            finally:
                _unlock(fd)
        finally:
            os.close(fd)

    @contextlib.contextmanager
    def edit(self) -> Iterator[dict]:
        with self._exclusive():
            data = self.read()
            before = {holder["ref"] for holder, _ in self._holders(data) if "ref" in holder}
            yield data
            stored = self._stored(data)
            tmp = self.path.with_name(self.path.name + ".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(stored, f, ensure_ascii=False, indent=2)
            _patiently(lambda: os.replace(tmp, self.path))
            # Only now does nothing point at the old ones.
            self._forget(before - {holder["ref"] for holder, _ in self._holders(stored) if "ref" in holder})
