from __future__ import annotations

import copy
import datetime as dt
import re
import threading
from collections.abc import Callable

from absorb.conversation.schemas import ConversationContext


_KEY = re.compile(r"^(?:line|web):[A-Za-z0-9_-]{16,128}$")


class MemoryContextStore:
    """Small process-local TTL store; no transcript or client-supplied user id.

    # ponytail: replace with a shared TTL store only when Cloud Run uses multiple
    # workers or instances that must share conversational context.
    """

    def __init__(self, *, ttl_seconds=1800, now: Callable[[], dt.datetime] | None = None):
        self.ttl_seconds = int(ttl_seconds)
        self.now = now or (lambda: dt.datetime.now(dt.timezone.utc))
        self._items: dict[str, ConversationContext] = {}
        self._claimed_actions: dict[str, dt.datetime] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _validate_key(key: str) -> str:
        if not isinstance(key, str) or _KEY.fullmatch(key) is None:
            raise ValueError("invalid conversation principal")
        return key

    def get(self, key: str) -> ConversationContext:
        key = self._validate_key(key)
        now = self.now()
        with self._lock:
            item = self._items.get(key)
            if item is None or item.expires_at is None or item.expires_at <= now:
                self._items.pop(key, None)
                return ConversationContext()
            return copy.deepcopy(item)

    def save(self, key: str, context: ConversationContext) -> None:
        key = self._validate_key(key)
        now = self.now()
        saved = copy.deepcopy(context)
        saved.updated_at = now
        saved.expires_at = now + dt.timedelta(seconds=self.ttl_seconds)
        with self._lock:
            self._items[key] = saved

    def clear(self, key: str) -> None:
        key = self._validate_key(key)
        with self._lock:
            self._items.pop(key, None)

    def claim_action(self, idempotency_key: str) -> bool:
        if not isinstance(idempotency_key, str) or len(idempotency_key) != 64:
            raise ValueError("invalid idempotency key")
        with self._lock:
            now = self.now()
            self._claimed_actions = {
                key: expires_at
                for key, expires_at in self._claimed_actions.items()
                if expires_at > now
            }
            if idempotency_key in self._claimed_actions:
                return False
            self._claimed_actions[idempotency_key] = now + dt.timedelta(seconds=self.ttl_seconds)
            return True

    def release_action(self, idempotency_key: str) -> None:
        with self._lock:
            self._claimed_actions.pop(idempotency_key, None)
