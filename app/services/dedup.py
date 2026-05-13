import time
from abc import ABC, abstractmethod
from collections.abc import Callable

from app.schemas.normalized import AlertGroup
from app.services.normalizer import stable_hash


class DedupStore(ABC):
    @abstractmethod
    async def seen(self, key: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def mark_seen(self, key: str, ttl_seconds: int) -> None:
        raise NotImplementedError


class InMemoryDedupStore(DedupStore):
    def __init__(self, time_func: Callable[[], float] = time.time) -> None:
        self._storage: dict[str, float] = {}
        self._time = time_func

    async def seen(self, key: str) -> bool:
        expires_at = self._storage.get(key)
        if expires_at is None:
            return False
        if expires_at <= self._time():
            self._storage.pop(key, None)
            return False
        return True

    async def mark_seen(self, key: str, ttl_seconds: int) -> None:
        self._cleanup()
        self._storage[key] = self._time() + ttl_seconds

    def clear(self) -> None:
        self._storage.clear()

    def _cleanup(self) -> None:
        now = self._time()
        expired = [key for key, expires_at in self._storage.items() if expires_at <= now]
        for key in expired:
            self._storage.pop(key, None)


def build_group_dedup_key(group: AlertGroup, route_chat_id: int) -> str:
    fingerprints = ",".join(sorted(f"{alert.fingerprint}:{alert.status}" for alert in group.alerts))
    return stable_hash(f"{route_chat_id}:{group.group_key}:{fingerprints}")
