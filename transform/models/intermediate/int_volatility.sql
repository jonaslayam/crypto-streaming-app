{{ config(materialized='view') }}

with base as (
    select * from {{ ref('stg_candles') }}
),

calc_stddev as (
    select
        SYMBOL,
        CANDLE_OPEN_TIME_UTC,
        CLOSE_PRICE,
        -- Volatilidad de 20 periodos
        STDDEV(CLOSE_PRICE) OVER (PARTITION BY SYMBOL ORDER BY CANDLE_OPEN_TIME_UTC ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as stddev_20,
        -- Necesitamos la SMA_20 aquí temporalmente solo para las matemáticas del Z-Score y Bollinger
        AVG(CLOSE_PRICE) OVER (PARTITION BY SYMBOL ORDER BY CANDLE_OPEN_TIME_UTC ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as sma_20
    from base
)

select
    SYMBOL,
    CANDLE_OPEN_TIME_UTC,
    stddev_20,
    case when stddev_20 = 0 then 0 else (CLOSE_PRICE - sma_20) / stddev_20 end as z_score_20,
    (sma_20 + (2 * stddev_20)) as bb_upper_20,
    (sma_20 - (2 * stddev_20)) as bb_lower_20
from calc_stddev