{{ config(materialized='table') }}

with base as ( select * from {{ ref('stg_candles') }} ),
     momentum as ( select * from {{ ref('int_price_momentum') }} ),
     volatility as ( select * from {{ ref('int_volatility') }} ),
     volume as ( select * from {{ ref('int_volume') }} ),
     rsi_atr as ( select * from {{ ref('int_rsi_atr') }} ) 

select
    -- 1. Identificadores Base
    b.SYMBOL,
    b.CANDLE_OPEN_TIME_CLT as timestamp_clt,
    b.CLOSE_PRICE,
    b.VOLUME,
    
    -- 2. Features de Momentum (Tendencia)
    m.sma_20,
    m.sma_50,
    m.sma_200,
    m.sma_720,
    
    -- 3. Features de Volatilidad (Rango y Extremos)
    v.stddev_20,
    v.z_score_20,
    v.bb_upper_20,
    v.bb_lower_20,
    ra.atr_14,
    
    -- 4. NUEVAS FEATURES V1.0 (Confirmación y Soporte)
    ra.rsi_14,          
    ra.rsi_24,          
    ra.z_score_24,       
    ra.range_pos_48h,    
    
    -- ---> LO NUEVO PARA LA SALIDA DINÁMICA DE FLINK <---
    -- Necesitamos el valor en dólares (o USDT) del techo y piso para las órdenes Limit
    ra.max_price_48h,    -- El precio exacto del techo (Trigger Take Profit)
    ra.min_price_48h,    -- El precio exacto del piso 
    
    -- 5. Otros
    vol.rvol_20,

    -- 6. VARIABLES OBJETIVO (Targets Históricos)
    -- NOTA DE ARQUITECTURA: Dejamos esto intacto. 
    -- Para las velas en vivo (hoy), esto dará NULL, lo cual usamos para saber que es el presente.
    -- Para las velas pasadas, calculará el target real para cuando quieras re-entrenar el modelo el próximo mes.
    (LEAD(b.CLOSE_PRICE, 24) OVER (PARTITION BY b.SYMBOL ORDER BY b.CANDLE_OPEN_TIME_UTC) - b.CLOSE_PRICE) / b.CLOSE_PRICE * 100 as target_return_24h,
    (LEAD(b.CLOSE_PRICE, 72) OVER (PARTITION BY b.SYMBOL ORDER BY b.CANDLE_OPEN_TIME_UTC) - b.CLOSE_PRICE) / b.CLOSE_PRICE * 100 as target_return_72h,
    (LEAD(b.CLOSE_PRICE, 168) OVER (PARTITION BY b.SYMBOL ORDER BY b.CANDLE_OPEN_TIME_UTC) - b.CLOSE_PRICE) / b.CLOSE_PRICE * 100 as target_return_168h

from base b
left join momentum m on b.SYMBOL = m.SYMBOL and b.CANDLE_OPEN_TIME_UTC = m.CANDLE_OPEN_TIME_UTC
left join volatility v on b.SYMBOL = v.SYMBOL and b.CANDLE_OPEN_TIME_UTC = v.CANDLE_OPEN_TIME_UTC
left join volume vol on b.SYMBOL = vol.SYMBOL and b.CANDLE_OPEN_TIME_UTC = vol.CANDLE_OPEN_TIME_UTC
left join rsi_atr ra on b.SYMBOL = ra.SYMBOL and b.CANDLE_OPEN_TIME_UTC = ra.CANDLE_OPEN_TIME_UTC