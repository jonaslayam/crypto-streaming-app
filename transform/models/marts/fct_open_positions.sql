{{ config(materialized='view') }}

with signals as (
    select * from {{ ref('fct_trading_signals') }}
),

closed_trades as (
    -- Esta tabla la alimenta Flink simulando el Exchange
    select symbol, entry_time 
    from {{ source('exchange_api', 'raw_executed_trades') }}
    where action = 'SELL'
),

open_trades as (
    select 
        s.SYMBOL,
        s.TIMESTAMP_CLT as entry_time,
        s.CLOSE_PRICE as entry_price,
        -- CAMBIO 1: signal -> signal_action
        s.signal_action as entry_type,
        -- CAMBIO 2: SUGGESTED_STOP_LOSS -> suggested_stop_loss (en minúsculas como en dbt)
        s.suggested_stop_loss as initial_stop
    from signals s
    left join closed_trades c 
      on s.symbol = c.symbol and s.timestamp_clt = c.entry_time
    -- CAMBIO 3: Actualizamos los nombres de las señales a los nuevos (ENTRY_...)
    where s.signal_action in ('ENTRY_STEADY', 'ENTRY_VOLATILE')
      and c.symbol is null -- CRÍTICO: Excluimos los que ya se vendieron
)

select * from open_trades