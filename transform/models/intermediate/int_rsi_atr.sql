{{ config(materialized='view') }}

with price_changes as (
    select 
        SYMBOL,
        CANDLE_OPEN_TIME_UTC,
        CLOSE_PRICE,
        HIGH_PRICE,
        LOW_PRICE,
        -- Diferencia de precio con la vela anterior
        CLOSE_PRICE - LAG(CLOSE_PRICE, 1) OVER (PARTITION BY SYMBOL ORDER BY CANDLE_OPEN_TIME_UTC) as price_change,
        -- True Range (TR) para el ATR
        GREATEST(
            HIGH_PRICE - LOW_PRICE,
            ABS(HIGH_PRICE - LAG(CLOSE_PRICE, 1) OVER (PARTITION BY SYMBOL ORDER BY CANDLE_OPEN_TIME_UTC)),
            ABS(LOW_PRICE - LAG(CLOSE_PRICE, 1) OVER (PARTITION BY SYMBOL ORDER BY CANDLE_OPEN_TIME_UTC))
        ) as true_range
    from {{ ref('stg_candles') }}
),

gains_losses as (
    select 
        pc.*,
        case when price_change > 0 then price_change else 0 end as gain,
        case when price_change < 0 then abs(price_change) else 0 end as loss
    from price_changes pc
),

averages as (
    select 
        gl.*,
        -- Medias Móviles Simples de 14 periodos para Ganancias y Pérdidas
        AVG(gain) OVER (PARTITION BY SYMBOL ORDER BY CANDLE_OPEN_TIME_UTC ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) as avg_gain_14,
        AVG(loss) OVER (PARTITION BY SYMBOL ORDER BY CANDLE_OPEN_TIME_UTC ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) as avg_loss_14,
        -- Cálculo del ATR
        AVG(true_range) OVER (PARTITION BY SYMBOL ORDER BY CANDLE_OPEN_TIME_UTC ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) as atr_14
    from gains_losses gl
)

select 
    SYMBOL,
    CANDLE_OPEN_TIME_UTC,
    atr_14,
    -- Fórmula final del RSI
    case 
        when avg_loss_14 = 0 then 100 
        else 100 - (100 / (1 + (avg_gain_14 / avg_loss_14))) 
    end as rsi_14
from averages