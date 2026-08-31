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
        -- Inferencia con SWING_XGB_72H_V2 (XGBoost, entrenado en
        -- transform/oml_models/v2_train_swing_xgb_72h.sql). Antes decía
        -- "modelo SVM de AutoML" y apuntaba a CRYPTO_MODEL_72H_V2, un
        -- nombre que no existe en ningún script de entrenamiento del repo.
        --
        -- La lista de columnas es la misma predictor_columns() que arma
        -- ml_train_data.sql/ml_test_data.sql (transform/macros/feature_set.sql).
        -- Antes decía "USING *" y arrastraba TODAS las columnas de
        -- fct_swing_features -- incluidos los TARGET_RETURN_* -- que en esta
        -- vela viva (TARGET_RETURN_72H is null, ver abajo) llegan en NULL:
        -- eso es el train/serve skew documentado en la auditoría.
        PREDICTION(SWING_XGB_72H_V2 USING {{ predictor_columns() | join(', ') }}) as pred_72h
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