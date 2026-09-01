-- dbt (and the OML training scripts under transform/oml_models/) connect
-- as this user, not TRADER_DATA -- keeping the raw-ingestion schema
-- separate from the transformation/ML one. Run as ADMIN, after
-- 01_setup_user.sql and 02_init_schema.sql.
CREATE USER DBT_ANALYTICS IDENTIFIED BY "${DBT_DB_PASSWORD}";
GRANT DWROLE TO DBT_ANALYTICS;
ALTER USER DBT_ANALYTICS QUOTA UNLIMITED ON DATA;

-- stg_candles.sql sources CRYPTO_CANDLES_1H from TRADER_DATA (see
-- transform/models/sources.yml) -- dbt needs read access across schemas
-- to build on top of it. Table-level, not schema-wide.
GRANT SELECT ON TRADER_DATA.CRYPTO_CANDLES_1H TO DBT_ANALYTICS;
