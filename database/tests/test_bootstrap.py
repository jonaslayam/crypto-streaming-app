"""Tests for the statement-splitting/substitution logic in bootstrap.py.

Doesn't touch a real Oracle instance -- oracledb.connect is mocked at
the same boundary as test_oracle_manager.py. What's actually under test
here is the part that's easy to get subtly wrong: that each script runs
as the right user (02_init_schema.sql must run as TRADER_DATA itself,
or the table ends up owned by ADMIN instead), and that password
placeholders get substituted before anything is sent to Oracle.
"""
import os
from unittest.mock import MagicMock, patch

import pytest

from database.scripts.bootstrap import main, run_script


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("ORACLE__DSN", "fake-dsn")
    monkeypatch.setenv("ORACLE_ADMIN_PASSWORD", "admin-pw")
    monkeypatch.setenv("TRADER_DATA_PASSWORD", "trader-pw")
    monkeypatch.setenv("DBT_ANALYTICS_PASSWORD", "dbt-pw")


def test_run_script_substitutes_password_placeholders(tmp_path):
    sql_file = tmp_path / "test.sql"
    sql_file.write_text('CREATE USER X IDENTIFIED BY "${DB_PASSWORD}";')
    os.environ["TRADER_DATA_PASSWORD"] = "s3cret"

    with patch("database.scripts.bootstrap.SCRIPTS_DIR", tmp_path), \
         patch("database.scripts.bootstrap.oracledb.connect") as connect:
        cursor = MagicMock()
        connect.return_value.cursor.return_value = cursor
        run_script("fake-dsn", "ADMIN", "admin-pw", "test.sql")

    executed_sql = cursor.execute.call_args[0][0]
    assert "s3cret" in executed_sql
    assert "${DB_PASSWORD}" not in executed_sql


def test_run_script_skips_empty_statements(tmp_path):
    sql_file = tmp_path / "test.sql"
    sql_file.write_text("SELECT 1 FROM DUAL;;;   ;\nSELECT 2 FROM DUAL;")

    with patch("database.scripts.bootstrap.SCRIPTS_DIR", tmp_path), \
         patch("database.scripts.bootstrap.oracledb.connect") as connect:
        cursor = MagicMock()
        connect.return_value.cursor.return_value = cursor
        run_script("fake-dsn", "ADMIN", "admin-pw", "test.sql")

    assert cursor.execute.call_count == 2


def test_main_runs_each_script_as_the_correct_user():
    """02_init_schema.sql has to run as TRADER_DATA, not ADMIN -- otherwise
    CRYPTO_CANDLES_1H ends up owned by ADMIN, and oracle_manager.py's
    unqualified `INSERT INTO CRYPTO_CANDLES_1H` would fail against it."""
    with patch("database.scripts.bootstrap.run_script") as run_script_mock:
        main()

    users_by_script = {call.args[3]: call.args[1] for call in run_script_mock.call_args_list}
    assert users_by_script["01_setup_user.sql"] == "ADMIN"
    assert users_by_script["02_init_schema.sql"] == "TRADER_DATA"
    assert users_by_script["03_setup_dbt_user.sql"] == "ADMIN"
