"""Tests for the Binance rate-limit tracker in backfill.py.

SmartDeepBackfill takes its Redis client directly through its
constructor, so these run against fakeredis without touching Binance,
Oracle, or a live Redis at all -- only the weight-counting logic is
under test.
"""
import fakeredis.aioredis as fakeredis
import pytest

from backfill import BINANCE_WEIGHT_LIMIT, SmartDeepBackfill


@pytest.fixture
async def backfill():
    fake_client = fakeredis.FakeRedis(decode_responses=True)
    instance = SmartDeepBackfill(client=None, oracle_manager=None, settings=None, redis_client=fake_client)
    yield instance
    await fake_client.aclose()


async def test_weight_starts_at_zero(backfill):
    assert await backfill.get_binance_weight() == 0


async def test_weight_accumulates_across_calls(backfill):
    await backfill.increment_binance_weight(cost=2)
    await backfill.increment_binance_weight(cost=5)
    assert await backfill.get_binance_weight() == 7


async def test_weight_key_carries_a_ttl(backfill):
    """The counter has to expire on its own -- Binance's own rate-limit
    window is 60 seconds, and this mirrors it so the pipeline throttles
    itself before Binance starts rejecting requests."""
    await backfill.increment_binance_weight(cost=1)
    ttl = await backfill.redis.ttl("binance:weight")
    assert 0 < ttl <= 60


async def test_wait_for_rate_limit_does_not_sleep_when_under_the_cap(backfill, monkeypatch):
    slept = []
    monkeypatch.setattr("backfill.asyncio.sleep", lambda s: slept.append(s))
    await backfill.increment_binance_weight(cost=BINANCE_WEIGHT_LIMIT - 1)
    await backfill.wait_for_rate_limit()
    assert slept == []


async def test_wait_for_rate_limit_sleeps_once_the_cap_is_reached(backfill, monkeypatch):
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr("backfill.asyncio.sleep", fake_sleep)
    await backfill.increment_binance_weight(cost=BINANCE_WEIGHT_LIMIT)
    await backfill.wait_for_rate_limit()
    assert slept == [60]
