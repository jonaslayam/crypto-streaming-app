{{ config(materialized='table') }}

with raw_predictions as (
    select
        SYMBOL, TIMESTAMP_CLT, CLOSE_PRICE, ATR_14, 
        RSI_14, SMA_20, SMA_200, Z_SCORE_20,
        RSI_24, Z_SCORE_24, RANGE_POS_48H,
        -- Eliminamos el modelo XGBoost de 24h. Solo usamos el nuevo SVM de AutoML.
        PREDICTION(CRYPTO_MODEL_72H_V2 USING *) as pred_72h
    from {{ ref('fct_swing_features') }}
    where TARGET_RETURN_72H is null -- Predicción para el futuro
)

select
    SYMBOL, TIMESTAMP_CLT, CLOSE_PRICE,
    round(pred_72h, 2) as pred_72h,
    case 
        -- 1. STEADY_GROWTH (El especialista en tendencias)
        -- Confiamos en el umbral alto del SVM (> 1.2)
        when pred_72h > 1.2 
             and CLOSE_PRICE > SMA_200 
             and RANGE_POS_48H < 0.45    
             and RSI_14 < 60 
             then 'STEADY_GROWTH'

        -- 2. VOLATILE_REVERSAL (El especialista en rebotes)
        -- Bajamos el umbral de predicción pero endurecemos el filtro de soporte (V1.0)
        when pred_72h > 0.6 
             and RANGE_POS_48H < 0.20   -- REGLA V1.0: Solo pegado al piso de 48h
             and RSI_14 < 50            -- Solo si hay espacio para subir
             then 'VOLATILE_REVERSAL'

        -- 3. ALERTA DE RIESGO
        -- Ajustado a la escala conservadora del SVM
        when pred_72h < -0.8 then 'BEARISH_ALERT'
        
        else 'HOLD/WAIT'
    end as signal,
    
    -- Gestión de Riesgo basada en la señal del SVM
    round(
        case 
            when pred_72h > 1.2 then CLOSE_PRICE - (1.5 * ATR_14)
            else CLOSE_PRICE - (2.0 * ATR_14)
        end, 2
    ) as suggested_stop_loss,
    
    -- Metadata para debug
    RANGE_POS_48H,
    Z_SCORE_24
from raw_predictions    