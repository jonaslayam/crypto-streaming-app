-- models/marts/fct_active_trade_limits.sql
{{ config(materialized='table') }}

with active_trades as (
    select * from {{ ref('fct_open_positions') }}
),
current_market as (
    -- AQUÍ ESTABA EL ERROR: Apuntamos a la tabla maestra que tiene todas las features
    select * from {{ ref('fct_swing_features') }} 
    qualify row_number() over (partition by SYMBOL order by timestamp_clt desc) = 1
)

select
    t.SYMBOL,
    t.entry_price,
    m.CLOSE_PRICE as current_price,
    
    -- 1. EL LÍMITE DE EMERGENCIA (Para Flink)
    ROUND(m.CLOSE_PRICE - (1.5 * m.ATR_14), 2) as trigger_stop_loss,
    
    -- 2. EL LÍMITE DE TOMA DE GANANCIAS (Para Flink)
    m.max_price_48h as trigger_take_profit,
    
    -- 3. EL GATILLO DE VOLATILIDAD (Para Flink)
    75 as trigger_rsi_panic,
    
    -- 4. LA DECISIÓN DEL GENERAL (Calculada por dbt)
    case 
        when PREDICTION(CRYPTO_MODEL_72H_V2 USING m.*) < 0.3 then 'SELL_NOW' 
        else 'HOLD' 
    end as ai_command

from active_trades t
join current_market m on t.SYMBOL = m.SYMBOL