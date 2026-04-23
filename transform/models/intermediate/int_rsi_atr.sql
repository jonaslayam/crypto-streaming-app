{{ config(materialized='view') }}

with price_changes as (
    select 
        SYMBOL,
        CANDLE_OPEN_TIME_UTC,
        CLOSE_PRICE,
        HIGH_PRICE,
        LOW_PRICE,
        -- Cambios para RSI
        CLOSE_PRICE - LAG(CLOSE_PRICE, 1) OVER (PARTITION BY SYMBOL ORDER BY CANDLE_OPEN_TIME_UTC) as price_change,
        -- True Range para ATR
        GREATEST(
            HIGH_PRICE - LOW_PRICE,
            ABS(HIGH_PRICE - LAG(CLOSE_PRICE, 1) OVER (PARTITION BY SYMBOL ORDER BY CANDLE_OPEN_TIME_UTC)),
            ABS(LOW_PRICE - LAG(CLOSE_PRICE, 1) OVER (PARTITION BY SYMBOL ORDER BY CANDLE_OPEN_TIME_UTC))
        ) as true_range,
        -- 1. SOPORTE Y RESISTENCIA V1.0 (Mínimo y Máximo de 48h)
        MIN(CLOSE_PRICE) OVER (PARTITION BY SYMBOL ORDER BY CANDLE_OPEN_TIME_UTC ROWS BETWEEN 47 PRECEDING AND CURRENT ROW) as min_48h,
        MAX(CLOSE_PRICE) OVER (PARTITION BY SYMBOL ORDER BY CANDLE_OPEN_TIME_UTC ROWS BETWEEN 47 PRECEDING AND CURRENT ROW) as max_48h
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
        -- Medias Móviles para RSI 14
        AVG(gain) OVER (PARTITION BY SYMBOL ORDER BY CANDLE_OPEN_TIME_UTC ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) as avg_gain_14,
        AVG(loss) OVER (PARTITION BY SYMBOL ORDER BY CANDLE_OPEN_TIME_UTC ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) as avg_loss_14,
        -- 2. CONFIRMACIÓN V1.0 (RSI 24 horas)
        AVG(gain) OVER (PARTITION BY SYMBOL ORDER BY CANDLE_OPEN_TIME_UTC ROWS BETWEEN 23 PRECEDING AND CURRENT ROW) as avg_gain_24,
        AVG(loss) OVER (PARTITION BY SYMBOL ORDER BY CANDLE_OPEN_TIME_UTC ROWS BETWEEN 23 PRECEDING AND CURRENT ROW) as avg_loss_24,
        -- 3. ESTADÍSTICA V1.0 (Z-Score 24 horas)
        AVG(CLOSE_PRICE) OVER (PARTITION BY SYMBOL ORDER BY CANDLE_OPEN_TIME_UTC ROWS BETWEEN 23 PRECEDING AND CURRENT ROW) as avg_price_24,
        STDDEV(CLOSE_PRICE) OVER (PARTITION BY SYMBOL ORDER BY CANDLE_OPEN_TIME_UTC ROWS BETWEEN 23 PRECEDING AND CURRENT ROW) as stddev_price_24,
        -- ATR
        AVG(true_range) OVER (PARTITION BY SYMBOL ORDER BY CANDLE_OPEN_TIME_UTC ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) as atr_14
    from gains_losses gl
)

select 
    SYMBOL,
    CANDLE_OPEN_TIME_UTC,
    atr_14,
    -- RSI 14 (El estándar)
    case when avg_loss_14 = 0 then 100 else 100 - (100 / (1 + (avg_gain_14 / avg_loss_14))) end as rsi_14,
    -- RSI 24 (Confirmación V1.0)
    case when avg_loss_24 = 0 then 100 else 100 - (100 / (1 + (avg_gain_24 / avg_loss_24))) end as rsi_24,
    -- Z-SCORE 24 (Desviación V1.0)
    round((CLOSE_PRICE - avg_price_24) / NULLIF(stddev_price_24, 0), 4) as z_score_24,
    -- 4. RANGE POSITION 48H (Proximidad al mínimo/máximo)
    round((CLOSE_PRICE - min_48h) / NULLIF(max_48h - min_48h, 0), 4) as range_pos_48h,
    
    -- ---> LO QUE FALTABA: Exponer los precios absolutos para Flink <---
    -- Les ponemos el alias exacto que fct_swing_features está esperando
    max_48h as max_price_48h,
    min_48h as min_price_48h

from averages