"""SQLite cache of raw API responses. A cache must never break the caller, so its failures read as misses."""

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, NamedTuple

# The table name carries the format version, a new format simply starts empty.
_SCHEMA = "create table if not exists cache_v1 (ns text, key text, value text, fetched_at real, primary key (ns, key))"


class Hit(NamedTuple):
    value: Any
    age: float


def _connect(path: Path | str) -> sqlite3.Connection:
    # The default busy timeout covers several processes sharing one cache.
    db = sqlite3.connect(path, check_same_thread=False)
    db.execute("pragma journal_mode=wal")
    db.execute(_SCHEMA)
    return db


class Store:
    def __init__(self, path: Path):
        self._lock = threading.Lock()
        try:
            self._db = _connect(path)
        except sqlite3.DatabaseError:
            # Corrupt or read-only. Nothing in here is precious, start over and stay in memory if the disk refuses.
            try:
                path.unlink(missing_ok=True)
                self._db = _connect(path)
            except (OSError, sqlite3.Error):
                self._db = _connect(":memory:")

    def get(self, ns: str, key: str) -> Hit | None:
        try:
            with self._lock:
                row = self._db.execute("select value, fetched_at from cache_v1 where ns = ? and key = ?", (ns, key)).fetchone()
        except sqlite3.Error:
            return None
        return Hit(json.loads(row[0]), time.time() - row[1]) if row else None

    def put(self, ns: str, key: str, value: Any) -> None:
        self._run("insert or replace into cache_v1 values (?, ?, ?, ?)", (ns, key, json.dumps(value, ensure_ascii=False), time.time()))

    def expire(self, ns: str) -> None:
        """Keep the rows as a fallback, but make the next read go to the network."""
        self._run("update cache_v1 set fetched_at = 0 where ns = ?", (ns,))

    def drop(self, ns: str) -> None:
        self._run("delete from cache_v1 where ns = ?", (ns,))

    def rename(self, old: str, new: str) -> None:
        self._run("update cache_v1 set ns = ? where ns = ?", (new, old))

    def _run(self, sql: str, args: tuple) -> None:
        try:
            with self._lock, self._db:
                self._db.execute(sql, args)
        except sqlite3.Error:
            pass

    def close(self) -> None:
        with self._lock:
            self._db.close()
