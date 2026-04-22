{{ config(materialized='view') }}

with raw_data as (
    select * from {{ source('binance_raw', 'CRYPTO_CANDLES_1H') }}
)

select
    SYMBOL,
    -- Convertimos milisegundos a TIMESTAMP en UTC primero
    (TO_TIMESTAMP('1970-01-01 00:00:00', 'YYYY-MM-DD HH24:MI:SS') + 
        NUMTODSINTERVAL(OPEN_TIME_MS / 1000, 'SECOND')) as candle_open_time_utc,
    
    -- Lo forzamos a la zona horaria de Santiago para consistencia analítica
    FROM_TZ(
        CAST(TO_TIMESTAMP('1970-01-01 00:00:00', 'YYYY-MM-DD HH24:MI:SS') + 
            NUMTODSINTERVAL(OPEN_TIME_MS / 1000, 'SECOND') AS TIMESTAMP), 
        'UTC'
    ) AT TIME ZONE 'America/Santiago' as candle_open_time_clt,
    
    OPEN_PRICE,
    HIGH_PRICE,
    LOW_PRICE,
    CLOSE_PRICE,
    VOLUME
from raw_data