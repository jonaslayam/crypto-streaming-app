"""One-time Oracle ADW bootstrap.

Creates the two schemas the rest of the project assumes already exist:
TRADER_DATA (raw candle ingestion -- producer/, processor/) and
DBT_ANALYTICS (dbt models, ml_train_data/ml_test_data, the OML model --
see 03_setup_dbt_user.sql for why they're separate).

Run this once, right after the ADW is provisioned, before `docker
compose up` or `dbt run`. It's a provisioning step, not something meant
to be re-run against a schema that already exists -- if TRADER_DATA or
DBT_ANALYTICS are already there, the CREATE USER statements fail loudly
rather than silently reusing whatever password is already set.

Each script runs connected as the user it needs to run as, not all as
ADMIN: 02_init_schema.sql has to execute as TRADER_DATA itself, or the
CRYPTO_CANDLES_1H table ends up owned by ADMIN instead -- and
oracle_manager.py inserts into it unqualified, assuming it owns the table.

Needs, in .env (see .env.example):
    ORACLE__DSN             -- the same ADW connect string the app uses
    ORACLE_ADMIN_PASSWORD   -- the ADW's ADMIN password (set at creation)
    TRADER_DATA_PASSWORD    -- password to set for the new TRADER_DATA user
    DBT_ANALYTICS_PASSWORD  -- password to set for the new DBT_ANALYTICS user

Usage:
    python database/scripts/bootstrap.py
"""
import os
from pathlib import Path

import oracledb
from dotenv import load_dotenv

load_dotenv()

SCRIPTS_DIR = Path(__file__).parent

SUBSTITUTIONS_ENV = {
    "${DB_PASSWORD}": "TRADER_DATA_PASSWORD",
    "${DBT_DB_PASSWORD}": "DBT_ANALYTICS_PASSWORD",
}


def run_script(dsn: str, user: str, password: str, filename: str) -> None:
    sql_text = (SCRIPTS_DIR / filename).read_text()
    for placeholder, env_var in SUBSTITUTIONS_ENV.items():
        sql_text = sql_text.replace(placeholder, os.environ[env_var])

    conn = oracledb.connect(user=user, password=password, dsn=dsn)
    conn.autocommit = True
    cursor = conn.cursor()
    try:
        for statement in sql_text.split(";"):
            statement = statement.strip()
            if not statement:
                continue
            label = next(
                (line for line in statement.splitlines() if not line.strip().startswith("--")),
                statement,
            )
            print(f"[{filename} as {user}] {label[:70]}")
            cursor.execute(statement)
    finally:
        conn.close()


REQUIRED_ENV_VARS = [
    "ORACLE__DSN",
    "ORACLE_ADMIN_PASSWORD",
    "TRADER_DATA_PASSWORD",
    "DBT_ANALYTICS_PASSWORD",
]


def main():
    # Fail before touching Oracle if anything's missing -- not partway
    # through, after TRADER_DATA and its table already exist.
    missing = [v for v in REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        raise SystemExit(f"Missing required environment variable(s): {', '.join(missing)}")

    dsn = os.environ["ORACLE__DSN"]
    admin_password = os.environ["ORACLE_ADMIN_PASSWORD"]
    trader_data_password = os.environ["TRADER_DATA_PASSWORD"]

    # 1. Create TRADER_DATA.
    run_script(dsn, "ADMIN", admin_password, "01_setup_user.sql")
    # 2. Create its table -- as TRADER_DATA itself, so it owns it.
    run_script(dsn, "TRADER_DATA", trader_data_password, "02_init_schema.sql")
    # 3. Create DBT_ANALYTICS and grant it read access to TRADER_DATA's table.
    run_script(dsn, "ADMIN", admin_password, "03_setup_dbt_user.sql")

    print("Done. TRADER_DATA and DBT_ANALYTICS are ready.")


if __name__ == "__main__":
    main()
