"""A tiny in-memory cache with expiry, for repeated non-sensitive results.

Why a cache at all: generating a quiz for "Python lists" gives the same answer
every time, and with a real model behind it that would be a paid API call every
time. Remembering the result for a few minutes turns the second request into a
dictionary lookup.

Why the cache is temporary and the database is permanent
-------------------------------------------------------
They answer different questions.

  * The cache answers "have I computed this recently?" It lives in the server's
    memory, disappears when the process restarts, and every entry expires after
    CACHE_TTL_SECONDS. Losing all of it costs nothing but a recomputation.

  * The database answers "what belongs to this user?" It lives on disk, survives
    restarts, and losing a row means losing someone's data for good.

So anything a user owns — accounts, conversations, messages — goes in the
database. Only shared, derivable, non-sensitive results go in the cache.

What is deliberately NOT cached
-------------------------------
Conversations and messages. Two reasons:

  1. Privacy. A cache keyed on content, shared across all callers, is exactly
     how one user's private text ends up in another user's response. Caching
     user-owned rows would undermine the ownership rule the rest of this project
     enforces.
  2. Correctness. Message history changes with every turn, so cached history
     would be stale almost immediately.

For a single process this dictionary is enough. Redis would be the next step
when several server processes need to share one cache — the interface here
(get/set with a TTL) is deliberately the same shape, so swapping it out means
rewriting this file only.
"""

import time
from threading import Lock
from typing import Any, Optional

from app import config


class TTLCache:
    """Key-value store where every entry expires after a fixed time."""

    def __init__(self, ttl_seconds: int = config.CACHE_TTL_SECONDS):
        self.ttl_seconds = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}

        # FastAPI serves requests from several threads, so two of them can touch
        # the dictionary at once. The lock keeps each operation atomic.
        self._lock = Lock()

        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        """Return the stored value, or None if absent or expired."""
        with self._lock:
            entry = self._store.get(key)

            if entry is None:
                self.misses += 1
                return None

            stored_at, value = entry

            # Expiry is checked on read rather than by a background timer, which
            # keeps this dependency-free. Stale entries simply never get served.
            if time.monotonic() - stored_at > self.ttl_seconds:
                del self._store[key]
                self.misses += 1
                return None

            self.hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        """Store a value under a key, replacing anything already there."""
        with self._lock:
            # time.monotonic() rather than time.time(): it always moves forward,
            # so a clock change or NTP adjustment cannot make entries look fresh
            # again or expire early.
            self._store[key] = (time.monotonic(), value)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self.hits = 0
            self.misses = 0

    def stats(self) -> dict:
        with self._lock:
            return {
                "entries": len(self._store),
                "hits": self.hits,
                "misses": self.misses,
                "ttl_seconds": self.ttl_seconds,
            }


# One shared instance for the whole process.
quiz_cache = TTLCache()
