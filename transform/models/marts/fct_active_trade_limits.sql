{{ config(
    materialized='table',
    description='Límites de salida dinámicos para posiciones abiertas'
) }}

with active_trades as (
    -- Esto viene de fct_open_positions.sql
    select * from {{ ref('fct_open_positions') }}
),

current_market as (
    select * from {{ ref('fct_swing_features') }} 
    qualify row_number() over (partition by SYMBOL order by TIMESTAMP_CLT desc) = 1
)

select
    t.SYMBOL,
    t.entry_price,
    t.entry_time,  -- <--- CAMBIADO: Antes decía entry_timestamp
    m.CLOSE_PRICE as current_price,
    
    -- 1. STOP LOSS DINÁMICO (3.5x ATR de Optuna)
    round(m.CLOSE_PRICE - ({{ var('stop_loss_atr_mult') }} * m.ATR_14), 4) as trigger_stop_loss,
    
    -- 2. TOMA DE GANANCIAS
    round(m.max_price_48h, 4) as trigger_take_profit,
    
    -- 3. GATILLO DE PÁNICO RSI
    75 as trigger_rsi_panic,
    
    -- 4. LA ORDEN DE LA IA (Deterioro optimizado)
    case 
        when PREDICTION(CRYPTO_MODEL_72H_V2 USING m.*) < {{ var('exit_ai_threshold') }} then 'SELL_NOW' 
        else 'HOLD' 
    end as ai_command,

    -- Metadata
    m.ATR_14,
    m.RSI_14,
    -- CAMBIADO: También aquí usamos entry_time
    round((CAST(CURRENT_TIMESTAMP AS DATE) - CAST(t.entry_time AS DATE)) * 24, 1) as hours_in_trade

from active_trades t
join current_market m on t.SYMBOL = m.SYMBOL