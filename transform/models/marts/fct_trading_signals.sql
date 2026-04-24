{{ config(
    materialized='table',
    alias='fct_trading_signals'
) }}

with raw_predictions as (
    select
        SYMBOL, 
        TIMESTAMP_CLT, 
        CLOSE_PRICE, 
        ATR_14, 
        RSI_14, 
        SMA_200, 
        RANGE_POS_48H,
        -- Inferencia con el modelo SVM de AutoML
        PREDICTION(CRYPTO_MODEL_72H_V2 USING *) as pred_72h
    from {{ ref('fct_swing_features') }}
    -- Filtramos para actuar solo sobre la data más reciente (sin target)
    where TARGET_RETURN_72H is null 
)

select
    SYMBOL, 
    TIMESTAMP_CLT, 
    CLOSE_PRICE,
    round(pred_72h, 4) as pred_72h,
    
    case 
        -- 1. ENTRADA: STEADY_GROWTH
        when pred_72h > {{ var('steady_pred_threshold') }} 
            and CLOSE_PRICE > SMA_200 
            and RANGE_POS_48H < {{ var('steady_range_threshold') }}    
            and RSI_14 < {{ var('steady_rsi_threshold') }} 
            then 'ENTRY_STEADY'

        -- 2. ENTRADA: VOLATILE_REVERSAL
        when pred_72h > {{ var('volatile_pred_threshold') }} 
            and RANGE_POS_48H < {{ var('volatile_range_threshold') }} 
            and RSI_14 < {{ var('volatile_rsi_threshold') }} 
            then 'ENTRY_VOLATILE'

        -- 3. SALIDA: IA_DETERIORO (Basado en tu exit_pred de Optuna)
        -- Si ya estamos dentro, este flag le dice al bot que cierre
        when pred_72h < {{ var('exit_ai_threshold') }} then 'EXIT_DETERIORO'

        -- 4. SALIDA: SOBRECOMPRA (Basado en tu backtest de DBeaver)
        when RSI_14 > 75 then 'EXIT_OVERBOUGHT'
        
        else 'HOLD'
    end as signal_action,
    
    -- Gestión de Riesgo Dinámica (Sincronizada con Optuna)
    -- Usamos el multiplicador 3.5 que salvó la rentabilidad
    round(CLOSE_PRICE - ({{ var('stop_loss_atr_mult') }} * ATR_14), 2) as suggested_stop_loss,
    
    -- Metadata para el bot de ejecución
    ATR_14,
    RANGE_POS_48H
from raw_predictions