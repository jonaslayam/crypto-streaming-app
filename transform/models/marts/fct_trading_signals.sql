{{ config(materialized='table') }}

with raw_predictions as (
    select
        SYMBOL, TIMESTAMP_CLT, CLOSE_PRICE, ATR_14, RSI_14, SMA_20, SMA_200, Z_SCORE_20,
        PREDICTION(SWING_XGB_24H_V1 USING *) as pred_24h,
        PREDICTION(SWING_XGB_72H_V2 USING *) as pred_72h
    from {{ ref('fct_swing_features') }}
    where TARGET_RETURN_24H is null
)

select
    SYMBOL, TIMESTAMP_CLT, CLOSE_PRICE,
    round(pred_24h, 2) as pred_24h,
    round(pred_72h, 2) as pred_72h,
    case 
        -- 1. STEADY_GROWTH (Antiguo Strong Swing): Tu señal más segura.
        -- La mantenemos tal cual porque nos dio el Profit Factor de 1.7
        when pred_72h > 8.0 
             and RSI_14 < 60 
             and CLOSE_PRICE > SMA_200 
             and Z_SCORE_20 < 1.8 
             then 'STEADY_GROWTH'

        -- 2. VOLATILE_REVERSAL (Antiguo Consistent Buy): Alta recompensa, baja probabilidad.
        -- Ajustamos el RSI un poco más abajo (62) para intentar subir ese 18% de win rate.
        when pred_24h > 1.5 
             and pred_72h > 3.0 
             and CLOSE_PRICE > SMA_20 
             and RSI_14 < 62 
             then 'VOLATILE_REVERSAL'

        -- 3. ALERTA DE RIESGO
        when pred_24h < -3.0 or pred_72h < -6.0 then 'BEARISH_ALERT'
        
        else 'HOLD/WAIT'
    end as signal,
    
    -- Ajuste de Riesgo: Usamos 1.5 ATR para la señal segura y 2.0 para la volátil
    round(
        case 
            when pred_72h > 8.0 then CLOSE_PRICE - (1.5 * ATR_14)
            else CLOSE_PRICE - (2.0 * ATR_14)
        end, 2
    ) as suggested_stop_loss
from raw_predictions