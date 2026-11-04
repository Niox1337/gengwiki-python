"""Saved API keys, the login token and subscribed tags, in one JSON file only this user can read."""

import contextlib
import json
import os
import threading
from pathlib import Path
from typing import Iterator

from .errors import GengWikiError


# ponytail: a plaintext 0600 file, same as ~/.aws/credentials. Move to the OS keychain if someone needs that.
class Keyring:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def read(self) -> dict:
        try:
            data = json.loads(self.path.read_text("utf-8"))
        except FileNotFoundError:
            data = {}
        except ValueError as e:
            # Secrets may be in there and are shown only once, so never overwrite this file.
            raise GengWikiError(f"{self.path} is not valid JSON, fix or delete it: {e}") from e
        data.setdefault("keys", {})
        return data

    @contextlib.contextmanager
    def edit(self) -> Iterator[dict]:
        # ponytail: locks this process only. Two processes saving at once lose one edit, a file lock fixes that.
        with self._lock:
            data = self.read()
            yield data
            tmp = self.path.with_name(self.path.name + ".tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
