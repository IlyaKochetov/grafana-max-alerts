import pytest

from app.services.dedup import InMemoryDedupStore


@pytest.mark.asyncio
async def test_in_memory_dedup_ttl() -> None:
    now = 1000.0

    def time_func() -> float:
        return now

    store = InMemoryDedupStore(time_func=time_func)

    assert await store.seen("key") is False
    await store.mark_seen("key", ttl_seconds=10)
    assert await store.seen("key") is True

    now = 1011.0
    assert await store.seen("key") is False
