{{ config(materialized='view') }}

with base as (
    select * from {{ ref('stg_candles') }}
)

select
    SYMBOL,
    CANDLE_OPEN_TIME_UTC,
    -- Relative Volume (RVOL): Volumen actual dividido por el promedio móvil de 20 periodos
    VOLUME / NULLIF(AVG(VOLUME) OVER (PARTITION BY SYMBOL ORDER BY CANDLE_OPEN_TIME_UTC ROWS BETWEEN 19 PRECEDING AND CURRENT ROW), 0) as rvol_20
from base