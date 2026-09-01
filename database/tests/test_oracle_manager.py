"""Tests for OracleManager's idempotent insert.

There's no live Oracle instance to test against in CI, so this can't
be a real integration test proving a duplicate row is actually
rejected server-side. What it can honestly verify: the exact SQL
OracleManager sends carries the IGNORE_ROW_ON_DUPKEY_INDEX hint against
the right index, executemany() runs once per batch, the connection
commits, and the reported count matches the cursor's rowcount -- the
contract this class is supposed to uphold, mocked at the oracledb
client boundary.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from database.oracle_manager import OracleManager


def _ctx_mock():
    """A MagicMock usable as a context manager (`with x() as y:`) that
    yields itself, matching how OracleManager uses pool.acquire() and
    connection.cursor(). Plain MagicMock() won't do this on its own --
    __enter__/__exit__ are auto-generated child mocks that return a
    fresh MagicMock by default, not the instance itself, so they need
    to be configured explicitly rather than overridden as a subclass
    method (which MagicMock's own magic-method machinery ignores)."""
    mock = MagicMock()
    mock.__enter__.return_value = mock
    mock.__exit__.return_value = False
    return mock


@pytest.fixture
def manager():
    config = SimpleNamespace(user="u", password="p", dsn="d")
    with patch("database.oracle_manager.oracledb.create_pool") as create_pool:
        create_pool.return_value = MagicMock()
        yield OracleManager(config)


def _mock_connection(manager, cursor):
    connection = _ctx_mock()
    connection.cursor.return_value = cursor
    manager.pool.acquire.return_value = connection
    return connection


def test_insert_uses_the_idempotency_hint(manager):
    cursor = _ctx_mock()
    cursor.rowcount = 3
    _mock_connection(manager, cursor)

    rows = [("BTCUSDT", 1, 1.0, 1.0, 1.0, 1.0, 1.0, 2, "live")]
    manager.insert_candles_batch(rows)

    sql_used = cursor.executemany.call_args[0][0]
    assert "IGNORE_ROW_ON_DUPKEY_INDEX(CRYPTO_CANDLES_1H, PK_CANDLES_1H)" in sql_used
    cursor.executemany.assert_called_once_with(sql_used, rows)


def test_insert_commits_and_returns_the_new_row_count(manager):
    cursor = _ctx_mock()
    cursor.rowcount = 2
    connection = _mock_connection(manager, cursor)

    result = manager.insert_candles_batch([("BTCUSDT", 1, 1, 1, 1, 1, 1, 2, "live")])

    assert result == 2
    connection.commit.assert_called_once()


def test_insert_swallows_oracle_errors_and_reports_zero(manager):
    import oracledb

    cursor = _ctx_mock()
    cursor.executemany.side_effect = oracledb.Error("simulated failure")
    _mock_connection(manager, cursor)

    result = manager.insert_candles_batch([("BTCUSDT", 1, 1, 1, 1, 1, 1, 2, "live")])
    assert result == 0


def test_get_last_timestamp_returns_none_when_symbol_has_no_rows(manager):
    cursor = _ctx_mock()
    cursor.fetchone.return_value = (None,)
    _mock_connection(manager, cursor)

    assert manager.get_last_timestamp("BTCUSDT") is None


def test_get_last_timestamp_returns_the_max_open_time(manager):
    cursor = _ctx_mock()
    cursor.fetchone.return_value = (1735689600000,)
    _mock_connection(manager, cursor)

    assert manager.get_last_timestamp("BTCUSDT") == 1735689600000
