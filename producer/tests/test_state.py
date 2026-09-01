"""Tests for the atomic compare-and-set in state.py.

Replaces the old producer/test_redis.py, which was a standalone script
(not discovered by pytest at all) that required a live Redis on
localhost and swallowed its own assertion failures inside a try/except
that only printed "Test fallido" instead of raising -- meaning even a
real Redis session running it manually could fail silently.

Runs against fakeredis instead of a live Redis: the CAS logic is a Lua
script, and fakeredis[lua] emulates Redis's own Lua interpreter closely
enough that this exercises the real update_if_newer() code path, not a
reimplementation of it.
"""
import fakeredis.aioredis as fakeredis
import pytest
import redis.asyncio as redis_asyncio

from state import RedisState


@pytest.fixture
async def redis_state(monkeypatch):
    fake_client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_asyncio.Redis, "from_pool", classmethod(lambda cls, pool: fake_client))

    state = RedisState(host="unused")
    yield state
    await state.close()


async def test_first_write_always_updates(redis_state):
    assert await redis_state.get_last_seen("BTCUSDT") == 0
    updated = await redis_state.update_if_newer("BTCUSDT", 100)
    assert updated is True
    assert await redis_state.get_last_seen("BTCUSDT") == 100


async def test_older_timestamp_is_rejected(redis_state):
    await redis_state.update_if_newer("BTCUSDT", 100)
    updated = await redis_state.update_if_newer("BTCUSDT", 50)
    assert updated is False
    assert await redis_state.get_last_seen("BTCUSDT") == 100


async def test_equal_timestamp_is_rejected(redis_state):
    """Strictly greater-than, not greater-or-equal -- a duplicate live
    tick for the same candle must not count as a new update."""
    await redis_state.update_if_newer("BTCUSDT", 100)
    updated = await redis_state.update_if_newer("BTCUSDT", 100)
    assert updated is False


async def test_newer_timestamp_updates_again(redis_state):
    await redis_state.update_if_newer("BTCUSDT", 100)
    updated = await redis_state.update_if_newer("BTCUSDT", 150)
    assert updated is True
    assert await redis_state.get_last_seen("BTCUSDT") == 150


async def test_symbols_are_tracked_independently(redis_state):
    await redis_state.update_if_newer("BTCUSDT", 100)
    await redis_state.update_if_newer("ETHUSDT", 999)
    assert await redis_state.get_last_seen("BTCUSDT") == 100
    assert await redis_state.get_last_seen("ETHUSDT") == 999
