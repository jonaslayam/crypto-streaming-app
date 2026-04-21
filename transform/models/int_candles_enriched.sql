{{ config(materialized='table') }}

with base as (
    select * from {{ ref('stg_candles') }}
),

enriched as (
    select
        t.*,
        -- Momentum (1 día aprox)
        AVG(t.CLOSE_PRICE) OVER (PARTITION BY t.SYMBOL ORDER BY t.CANDLE_OPEN_TIME_UTC ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as sma_20,
        
        -- Estructural (2 días aprox)
        AVG(t.CLOSE_PRICE) OVER (PARTITION BY t.SYMBOL ORDER BY t.CANDLE_OPEN_TIME_UTC ROWS BETWEEN 49 PRECEDING AND CURRENT ROW) as sma_50,
        
        -- Macro / Soporte fuerte (1 semana+)
        AVG(t.CLOSE_PRICE) OVER (PARTITION BY t.SYMBOL ORDER BY t.CANDLE_OPEN_TIME_UTC ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) as sma_200,
        
        -- Volatilidad (Desviación estándar para el Z-Score)
        STDDEV(t.CLOSE_PRICE) OVER (PARTITION BY t.SYMBOL ORDER BY t.CANDLE_OPEN_TIME_UTC ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) as stddev_20
    from base t
)

select 
    e.*,
    -- Cálculo del Z-Score (Cuán lejos estamos de la media de 20)
    case 
        when stddev_20 = 0 then 0 
        else (CLOSE_PRICE - sma_20) / stddev_20 
    end as z_score_20
from enriched e